"""Portrait seek geometry and non-activating song selection/stop handoff."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from nte_music_desk import cli
from nte_music_desk.paths import asset_dir
from nte_music_desk.ui import App


@unittest.skipUnless(sys.platform=='win32','Windows mini player')
class MiniSongControlsChecks(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.folder=Path(temp.name);root=tk.Tk();root.withdraw()
        self.app=App(root,SimpleNamespace(ROOT=self.folder,ASSETS=asset_dir(),key_schedule=cli.key_schedule))
        self.addCleanup(self.app.close)
        self.mini=self.app.mini

    def song(self,name):
        path=self.folder/(name+'.mid')
        path.write_bytes((asset_dir()/'scores/twinkle.mid').read_bytes())
        self.app.preferences.setdefault('shelf_files',[]).append({'path':str(path),'title':name})
        return path

    def playing(self,paused=False):
        self.app.active={'control':self.folder/'control.json','cancel':self.folder/'stop',
            'progress':self.folder/'progress.json','length':30,'origin':0,'speed':1,'elapsed':2,
            'phase':'paused' if paused else 'playing','pause_requested':paused,'control_sequence':0}
        return self.app.active

    def finish_old(self,code=2,reason='收到工作台停止指令，已停止。'):
        self.app.handle_message({'kind':'game_done','code':code,
            'result':{'status':'stopped' if code==2 else 'error','elapsed':2,'control_sequence':0,'reason':reason}})

    def test_portrait_track_and_seek_use_the_same_padded_geometry(self):
        self.mini.show();self.app.root.update()
        canvas=self.mini.progress;width=canvas.winfo_width()
        self.assertEqual(canvas.avatar.width(),26)
        self.assertEqual(canvas.fraction_at(18),0)
        self.assertEqual(canvas.fraction_at(width-18),1)
        for fraction in (0,.5,1):
            self.app.progress.set(fraction*100);self.mini.refresh()
            x,y=canvas.coords('portrait')
            self.assertAlmostEqual(x,18+(width-36)*fraction)
            self.assertGreaterEqual(x-15,0);self.assertLessEqual(x+15,width)
        self.app.seek_drag={'canvas':canvas,'frame':self.app.position_frame(),'song':self.app.song_fingerprint,'paused':False}
        event=SimpleNamespace(widget=canvas,x=18)
        self.app.move_seek(event);self.assertEqual(self.app.progress.get(),0)
        event.x=width-18;self.app.end_seek(event)
        self.assertAlmostEqual(self.app.progress.get(),100)
        self.assertLessEqual(self.mini.play.winfo_rooty()+self.mini.play.winfo_height(),
                             self.mini.window.winfo_rooty()+self.mini.window.winfo_height())

    def test_song_dropdown_shows_library_and_scrolls_without_changing_foreground(self):
        songs=[self.song('曲目'+str(i)) for i in range(9)]
        self.app.preferences['shelf_hidden']=[str(songs[0])]
        self.app.open_path(songs[1]);self.mini.show();self.app.root.update()
        u=self.mini.native.user32;foreground=u.GetForegroundWindow()
        self.mini.toggle_songs();self.app.root.update()
        popup=self.mini.songs
        self.assertIsNotNone(popup)
        self.assertEqual(u.GetForegroundWindow(),foreground)
        self.assertTrue(u.IsWindowVisible(popup.native.hwnd))
        self.assertGreaterEqual(popup.window.winfo_rooty(),
                                self.mini.window.winfo_rooty()+self.mini.window.winfo_height())
        self.assertNotIn(songs[0],[p for _,p in popup.buttons])
        selected=next(b for b,p in popup.buttons if p==songs[1])
        self.assertTrue(selected.cget('text').startswith('✓'))
        popup.canvas.yview_moveto(1);self.app.root.update_idletasks()
        self.assertGreater(popup.canvas.yview()[0],0)
        self.mini.hide();self.assertIsNone(self.mini.songs)
        self.assertFalse(popup.window.winfo_exists())

    def test_idle_selection_loads_without_starting_a_game(self):
        target=self.song('新曲')
        self.mini.show();self.app.root.update()
        foreground=self.mini.native.user32.GetForegroundWindow()
        self.mini.toggle_songs();self.app.root.update()
        with patch.object(self.app,'play') as play:
            next(b for b,p in self.mini.songs.buttons if p==target).invoke()
            self.assertEqual(self.app.current_path,target)
            play.assert_not_called()
            self.assertEqual(self.mini.native.user32.GetForegroundWindow(),foreground)

    def test_playing_selection_waits_for_key_release_before_loading_and_restarting(self):
        target=self.song('下一曲');original=self.app.current_path;active=self.playing()
        with patch.object(self.app,'play') as play:
            self.mini.choose_song(target)
            self.assertEqual(self.app.current_path,original)
            self.assertIs(self.app.active,active)
            self.assertTrue(active['cancel'].is_file())
            play.assert_not_called()
            self.finish_old()
            self.assertEqual(self.app.current_path,target)
            self.assertIsNone(self.mini.pending_song)
            play.assert_called_once_with(None)

    def test_paused_selection_loads_without_auto_resuming(self):
        target=self.song('暂停后换曲');self.playing(paused=True)
        with patch.object(self.app,'play') as play:
            self.mini.choose_song(target);self.finish_old()
            self.assertEqual(self.app.current_path,target);play.assert_not_called()

    def test_explicit_stop_cancels_queued_switch_and_rapid_selection_uses_latest(self):
        b,c=self.song('B'),self.song('C');original=self.app.current_path
        self.playing()
        with patch.object(self.app,'play') as play:
            self.mini.choose_song(b);self.mini.choose_song(c)
            self.assertEqual(self.mini.pending_song,(c,True))
            self.app.stop();self.finish_old()
            self.assertEqual(self.app.current_path,original);play.assert_not_called()
            self.playing()
            self.mini.choose_song(b);self.mini.choose_song(c);self.finish_old()
            self.assertEqual(self.app.current_path,c);play.assert_called_once_with(None)

    def test_missing_or_same_song_does_not_interrupt_and_focus_loss_does_not_restart(self):
        active=self.playing();original=self.app.current_path
        self.mini.choose_song(original)
        self.assertFalse(active['cancel'].exists())
        self.mini.choose_song(self.folder/'missing.mid')
        self.assertIs(self.app.active,active)
        self.assertIsNone(self.mini.pending_song)
        target=self.song('B')
        with patch.object(self.app,'play') as play:
            self.mini.choose_song(target);self.finish_old(reason='检测到 F8，已停止。')
            self.assertEqual(self.app.current_path,target);play.assert_not_called()

    def test_dropdown_opens_above_when_player_is_at_bottom_edge(self):
        for i in range(6):self.song('曲目'+str(i))
        left,top,width,height=self.mini.screen_bounds()
        self.mini.position=self.mini.clamp(left+width,top+height)
        self.mini.show();self.app.root.update()
        self.mini.toggle_songs();self.app.root.update()
        popup=self.mini.songs.window
        self.assertGreaterEqual(popup.winfo_rooty(),top)
        self.assertLessEqual(popup.winfo_rooty()+popup.winfo_height(),top+height)
        self.assertLessEqual(popup.winfo_rooty()+popup.winfo_height(),self.mini.window.winfo_rooty())

    def test_safety_modifier_unknown_stop_and_process_failure_never_restart(self):
        target=self.song('安全停止后换曲')
        for code,reason,origin in ((2,'检测到 Alt 按下，已停止；请松开修饰键后重试。','safety'),
                                   (2,'检测到 Ctrl 按下，已停止；请松开修饰键后重试。','safety'),
                                   (2,'未知停止原因',None),(1,'播放进程异常',None)):
            with self.subTest(reason=reason),patch.object(self.app,'play') as play:
                self.app.open_path(self.app.assets/'scores/twinkle.mid')
                self.playing();self.mini.choose_song(target)
                self.app.handle_message({'kind':'game_done','code':code,
                    'result':{'status':'stopped' if code==2 else 'error','reason':reason,'stop_origin':origin}})
                self.assertEqual(self.app.current_path,target)
                self.assertIsNone(self.app.active);play.assert_not_called()

    def test_target_disappearing_or_becoming_invalid_during_handoff_keeps_old_song(self):
        original=self.app.current_path
        for mode in ('missing','corrupt'):
            with self.subTest(mode=mode),patch.object(self.app,'play') as play,patch.object(self.app,'show_error') as error:
                target=self.song(mode);self.playing();self.mini.choose_song(target)
                if mode=='missing':target.unlink()
                else:target.write_bytes(b'not a MIDI')
                self.finish_old()
                self.assertEqual(self.app.current_path,original)
                self.assertIsNone(self.mini.pending_song);self.assertIsNone(self.app.active)
                error.assert_called_once();play.assert_not_called()

    def test_empty_library_and_play_button_dismissal(self):
        self.app.preferences['shelf_hidden']=[str(p) for _,p,_ in self.app.library_entries()]
        self.mini.toggle_songs()
        self.assertIsNone(self.mini.songs);self.assertIn('列表为空',self.mini.notice)
        self.app.preferences['shelf_hidden']=[]
        self.mini.show();self.app.root.update();self.mini.toggle_songs()
        self.assertIsNotNone(self.mini.songs)
        with patch.object(self.app,'play') as play:
            self.mini.toggle();play.assert_called_once_with(None)
        self.assertIsNone(self.mini.songs)
