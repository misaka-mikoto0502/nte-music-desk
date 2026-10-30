// Copyright NTE Music Desk contributors. MIT.
using System;
using System.IO;
using System.Drawing;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Windows.Forms;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

class AudioWindow : Form {
    readonly Uri home;
    readonly string profile, report;
    readonly bool diagnostic;
    readonly bool cancelCheck;
    readonly string diagnosticProfile;
    readonly int diagnosticAlign;
    WebView2 view;
    string diagnosticData;
    readonly List<object> layoutChecks=new List<object>();
    readonly JavaScriptSerializer json = new JavaScriptSerializer();
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [STAThread] static int Main(string[] args) {
        Uri uri;
        if (args.Length < 3 || !Uri.TryCreate(args[0], UriKind.Absolute, out uri) ||
            uri.Scheme != "http" || uri.Host != "127.0.0.1" || uri.Port < 1 ||
            !uri.AbsolutePath.EndsWith("/") || uri.UserInfo.Length != 0 || uri.Query.Length != 0 || uri.Fragment.Length != 0) return 2;
        SetProcessDPIAware(); Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        bool test=args.Length>=4 && (args[3]=="--diagnostic" || args[3]=="--diagnostic-cancel");
        string preset=args.Length>=5?args[4]:"polyphonic";
        int align=args.Length>=6 && args[5]=="24"?24:0;
        if(preset!="polyphonic" && preset!="detail" && preset!="melody")return 2;
        Application.Run(new AudioWindow(uri,args[1],args[2],test,test && args[3]=="--diagnostic-cancel",preset,align));
        return Environment.ExitCode;
    }
    AudioWindow(Uri url,string userData,string state,bool test,bool cancel,string preset,int align) {
        home=url; profile=userData; report=state; diagnostic=test;
        cancelCheck=cancel;diagnosticProfile=preset;diagnosticAlign=align;
        Text="音频转谱 · 异环演奏工作台";
        BackColor=Color.FromArgb(238,238,231);
        StartPosition=FormStartPosition.CenterScreen;
        ClientSize=new Size(Math.Min(1280,Screen.PrimaryScreen.WorkingArea.Width-80),Math.Min(800,Screen.PrimaryScreen.WorkingArea.Height-100));
        MinimumSize=new Size(900,650);
        if(diagnostic){ShowInTaskbar=false;StartPosition=FormStartPosition.Manual;Location=new Point(-10000,-10000);}
        var icon=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","icon.ico");
        if(File.Exists(icon))Icon=new Icon(icon);
        var waiting=new Label {Text="正在打开本地音频转谱…",AutoSize=true,Location=new Point(32,32)};
        Controls.Add(waiting);
        Shown+=async (s,e)=> {
            // Commands use a private inherited pipe; no global window lookup.
            var commands=new Thread(()=> {
                try { string command; while((command=Console.In.ReadLine())!=null) {
                    var value=command;
                    BeginInvoke((Action)(()=> { if(value=="close")Close(); else if(value=="show") {WindowState=FormWindowState.Normal;Show();Activate();} }));
                } BeginInvoke((Action)(()=>Close())); } catch { }
            }); commands.IsBackground=true; commands.Start();
            try {
                view=new WebView2 {Dock=DockStyle.Fill};Controls.Add(view);view.BringToFront();
                var env=await CoreWebView2Environment.CreateAsync(null,profile);
                await view.EnsureCoreWebView2Async(env);
                var core=view.CoreWebView2;
                core.Settings.AreHostObjectsAllowed=false;
                core.Settings.IsWebMessageEnabled=diagnostic;
                core.Settings.AreDevToolsEnabled=false;
                core.Settings.AreDefaultContextMenusEnabled=false;
                core.Settings.AreDefaultScriptDialogsEnabled=false;
                core.NavigationStarting+=(a,b)=> {if(!Local(b.Uri))b.Cancel=true;};
                core.FrameNavigationStarting+=(a,b)=> {b.Cancel=true;};
                core.NewWindowRequested+=(a,b)=> {b.Handled=true;if(b.Uri==new Uri(home,"licenses.txt").AbsoluteUri)Process.Start(new ProcessStartInfo(b.Uri){UseShellExecute=true});};
                core.PermissionRequested+=(a,b)=> {b.State=CoreWebView2PermissionState.Deny;};
                core.AddWebResourceRequestedFilter("*",CoreWebView2WebResourceContext.All);
                core.WebResourceRequested+=(a,b)=> {
                    var address=b.Request.Uri;
                    if((address.StartsWith("http:") || address.StartsWith("https:")) && !Local(address))
                        b.Response=env.CreateWebResourceResponse(new MemoryStream(),403,"Local files only","Content-Type: text/plain");
                };
                core.DownloadStarting+=(a,b)=> {
                    if(!Local(b.DownloadOperation.Uri) || !b.DownloadOperation.Uri.StartsWith(new Uri(home,"results/").AbsoluteUri,StringComparison.Ordinal)) {b.Cancel=true;return;}
                    try {
                    var folder=Microsoft.Win32.Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders","{374DE290-123F-4565-9164-39C4925E467B}",null) as string;
                    folder=folder==null?Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"Downloads"):Environment.ExpandEnvironmentVariables(folder);
                    if(diagnostic)folder=Path.Combine(Path.GetDirectoryName(report),"downloads");
                    Directory.CreateDirectory(folder);
                    var name=Path.GetFileName(b.ResultFilePath);
                    if(!name.EndsWith(".mid",StringComparison.OrdinalIgnoreCase))name="轻量转谱.mid";
                    var target=Path.Combine(folder,name);int suffix=1;
                    while(File.Exists(target))target=Path.Combine(folder,Path.GetFileNameWithoutExtension(name)+" ("+(suffix++)+").mid");
                    b.ResultFilePath=target;b.Handled=true;
                    var operation=b.DownloadOperation;
                    operation.StateChanged+=(x,y)=> {
                        if(operation.State==CoreWebView2DownloadState.Completed) {
                            if(diagnostic){State(new {state="diagnostic",data=diagnosticData,download=target,layout=layoutChecks});Close();}
                            else if(core.Source==home.AbsoluteUri)core.ExecuteScriptAsync("document.getElementById('download-status').textContent='MIDI 已保存到系统下载文件夹，工作台另有副本。';");
                        } else if(operation.State==CoreWebView2DownloadState.Interrupted) {
                            if(diagnostic){State(new {state="error",error="MIDI download interrupted"});Close();}
                            else if(core.Source==home.AbsoluteUri)core.ExecuteScriptAsync("document.getElementById('download-status').textContent='下载未完成，可再次点击下载；工作台副本已保留。';");
                        }
                    };
                    } catch(Exception error) {
                        b.Cancel=true;State(new {state="download_error",error=error.Message});
                        if(diagnostic)Close();
                    }
                };
                core.NavigationCompleted+=async (a,b)=> {
                    if(!b.IsSuccess){if(diagnosticData==null)State(new {state="error",error=b.WebErrorStatus.ToString()});return;}
                    State(new {state="ready",runtime=env.BrowserVersionString});
                    if(diagnostic && core.Source==home.AbsoluteUri) {
                        // Developer check calls the shared production pipeline, without UI input.
                        var code=@"(async()=>{try{
                          const s=await(await fetch('state')).json();
                          const blob=await(await fetch('input/'+s.desktop_file.id)).blob();
                          const phases=[];
                          const controller=new AbortController();
                          const result=await NteAudio.convertFile(new File([blob],s.desktop_file.name,{type:blob.type}),__SETTINGS__,
                            {signal:controller.signal,onEvent:e=>{phases.push(e);if(__CANCEL__ && e.phase==='inference' && e.progress>0)controller.abort();}});
                          chrome.webview.postMessage(JSON.stringify({result,phases}));
                        }catch(e){chrome.webview.postMessage(JSON.stringify({error:String(e),cancelled:e.name==='AbortError'}));}})();";
                        await core.ExecuteScriptAsync(code.Replace("__SETTINGS__",json.Serialize(new {profile=diagnosticProfile,align_ms=diagnosticAlign})).Replace("__CANCEL__",cancelCheck?"true":"false"));
                    }
                };
                if(diagnostic)core.WebMessageReceived+=async (a,b)=> {
                    if(b.Source!=home.AbsoluteUri)return;
                    try {
                        diagnosticData=b.TryGetWebMessageAsString();
                        var data=json.Deserialize<Dictionary<string,object>>(diagnosticData);
                        if(data.ContainsKey("cancelled") && (bool)data["cancelled"]){State(new {state="cancelled",data=diagnosticData});Close();return;}
                        if(data.ContainsKey("error")){State(new {state="error",error=data["error"]});Close();return;}
                        var result=(Dictionary<string,object>)data["result"];
                        var download=new Uri(home,(string)result["result"]).AbsoluteUri;
                        if(!Local(download) || !download.StartsWith(new Uri(home,"results/").AbsoluteUri,StringComparison.Ordinal))throw new Exception("Invalid result route");
                        await Task.Delay(1800); // Allow ordinary result restoration to render.
                        MinimumSize=Size.Empty;
                        foreach(var size in new[]{new Size(1280,720),new Size(1000,650),new Size(900,600)}) {
                            ClientSize=size;await Task.Delay(100);
                            var width=Convert.ToDouble(json.DeserializeObject(await core.ExecuteScriptAsync("innerWidth")));
                            view.ZoomFactor=view.ZoomFactor*width/size.Width;
                            await Task.Delay(150);
                            layoutChecks.Add(json.DeserializeObject(await core.ExecuteScriptAsync(@"(()=>{
                              const r=e=>e.getBoundingClientRect();const p=r(document.querySelector('.result')),f=r(document.querySelector('footer'));
                              const d=r(document.getElementById('download')),s=r(document.querySelector('.settings'));
                              return {width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,
                              panelBottom:p.bottom,footerTop:f.top,downloadVisible:d.height>0,settingsOverflow:document.querySelector('.settings').scrollHeight>s.height,
                              resultOverflow:document.querySelector('.result').scrollHeight>p.height};})()")));
                        }
                        core.Navigate(download);
                    } catch(Exception error){State(new {state="error",error=error.Message});Close();}
                };
                core.Navigate(home.AbsoluteUri);
            } catch(Exception error) {
                State(new {state="error",error=error.Message}); Environment.ExitCode=3;
                if(view!=null){Controls.Remove(view);view.Dispose();view=null;}
                waiting.Text="无法打开桌面转谱组件。请确认已安装 Microsoft Edge WebView2 Runtime。\n也可使用文件菜单中的“轻量转谱（浏览器兼容）”。\n\n"+error.Message;
            }
        };
        FormClosed+=(s,e)=> {if(view!=null)view.Dispose();};
    }
    bool Local(string address) {
        Uri uri;return Uri.TryCreate(address,UriKind.Absolute,out uri) && uri.Scheme==home.Scheme &&
            uri.Host==home.Host && uri.Port==home.Port && uri.AbsolutePath.StartsWith(home.AbsolutePath,StringComparison.Ordinal) && uri.UserInfo.Length==0;
    }
    void State(object data) {try {Directory.CreateDirectory(Path.GetDirectoryName(report));File.WriteAllText(report,json.Serialize(data));}catch {}}
}
