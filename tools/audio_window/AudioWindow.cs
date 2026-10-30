// Copyright NTE Music Desk contributors. MIT.
using System;
using System.IO;
using System.Drawing;
using System.Diagnostics;
using System.Threading;
using System.Windows.Forms;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

class AudioWindow : Form {
    readonly Uri home;
    readonly string profile, report;
    readonly bool diagnostic;
    WebView2 view;
    readonly JavaScriptSerializer json = new JavaScriptSerializer();
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [STAThread] static int Main(string[] args) {
        Uri uri;
        if (args.Length < 3 || !Uri.TryCreate(args[0], UriKind.Absolute, out uri) ||
            uri.Scheme != "http" || uri.Host != "127.0.0.1" || uri.Port < 1 ||
            !uri.AbsolutePath.EndsWith("/") || uri.UserInfo.Length != 0 || uri.Query.Length != 0 || uri.Fragment.Length != 0) return 2;
        SetProcessDPIAware(); Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new AudioWindow(uri,args[1],args[2],args.Length==4 && args[3]=="--diagnostic"));
        return Environment.ExitCode;
    }
    AudioWindow(Uri url,string userData,string state,bool test) {
        home=url; profile=userData; report=state; diagnostic=test;
        Text="音频转谱 · 异环演奏工作台";
        BackColor=Color.FromArgb(238,238,231);
        StartPosition=FormStartPosition.CenterScreen;
        ClientSize=new Size(Math.Min(1280,Screen.PrimaryScreen.WorkingArea.Width-80),Math.Min(800,Screen.PrimaryScreen.WorkingArea.Height-100));
        MinimumSize=new Size(900,650);
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
                    var folder=Microsoft.Win32.Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders","{374DE290-123F-4565-9164-39C4925E467B}",null) as string;
                    folder=folder==null?Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"Downloads"):Environment.ExpandEnvironmentVariables(folder);
                    Directory.CreateDirectory(folder);
                    var name=Path.GetFileName(b.ResultFilePath);
                    if(!name.EndsWith(".mid",StringComparison.OrdinalIgnoreCase))name="轻量转谱.mid";
                    var target=Path.Combine(folder,name);int suffix=1;
                    while(File.Exists(target))target=Path.Combine(folder,Path.GetFileNameWithoutExtension(name)+" ("+(suffix++)+").mid");
                    b.ResultFilePath=target;b.Handled=true;
                };
                core.NavigationCompleted+=async (a,b)=> {
                    if(!b.IsSuccess){State(new {state="error",error=b.WebErrorStatus.ToString()});return;}
                    State(new {state="ready",runtime=env.BrowserVersionString});
                    if(diagnostic && core.Source==home.AbsoluteUri) {
                        // Developer-only inference check on a preselected local fixture.
                        // It calls the production worker directly, without UI input.
                        await core.ExecuteScriptAsync(@"(async()=>{try{
                          const s=await(await fetch('state')).json();
                          const data=await(await fetch('input/'+s.desktop_file.id)).arrayBuffer();
                          const c=new AudioContext();const decoded=await c.decodeAudioData(data);await c.close();
                          const o=new OfflineAudioContext(1,Math.ceil(decoded.duration*22050),22050);
                          const source=o.createBufferSource();source.buffer=decoded;source.connect(o.destination);source.start();
                          const samples=(await o.startRendering()).getChannelData(0).slice();
                          const w=new Worker('worker.js');w.onmessage=({data})=>{if(data.result||data.error)chrome.webview.postMessage(JSON.stringify(data));};
                          w.postMessage({samples,model:new URL('model.json',location.href).href,profile:'polyphonic'},[samples.buffer]);
                        }catch(e){chrome.webview.postMessage(JSON.stringify({error:String(e)}));}})();");
                    }
                };
                if(diagnostic)core.WebMessageReceived+=(a,b)=> {if(b.Source==home.AbsoluteUri) {State(new {state="diagnostic",data=b.TryGetWebMessageAsString()});Close();}};
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
