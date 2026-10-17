import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from nte_music_desk.notation import parse_musicxml,read_score,unpack_mxl,xml_root
from nte_music_desk.midi import read_midi,write_midi
from nte_music_desk.paths import asset_dir


def note(step="C",duration=1,extra="",octave=4):
    return f'<note>{extra}<pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>{duration}</duration></note>'


def score(content):
    return ('<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1">'+content+'</part></score-partwise>').encode()


class NotationChecks(unittest.TestCase):
    def test_polyphony_ties_rests_and_tempo(self):
        body=('<measure><attributes><divisions>2</divisions></attributes><direction><sound tempo="60"/></direction>'+
              note('C',2)+note('E',2,'<chord/>')+'<note><rest/><duration>2</duration></note>'+
              note('F',4,'<tie type="start"/>')+'</measure><measure>'+note('F',2,'<tie type="stop"/>')+
              '<direction><sound tempo="120"/></direction>'+note('D',6)+'<backup><duration>8</duration></backup>'+note('G',8,octave=3)+'</measure>')
        song=parse_musicxml(score(body))
        self.assertEqual([(n.pitch,round(n.start,4),round(n.end,4)) for n in song.notes],
                         [(60,0,1),(64,0,1),(65,2,5),(55,4,6.5),(62,5,6.5)])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'converted.mid';write_midi(song,path)
            result=read_midi(path)
            for a,b in zip(song.notes,result.notes):
                self.assertEqual(a.pitch,b.pitch)
                self.assertAlmostEqual(a.start,b.start,places=3)
                self.assertAlmostEqual(a.end,b.end,places=3)

    def test_repeats_numbered_endings_and_tempo_restore(self):
        body=('<measure><barline location="left"><repeat direction="forward"/></barline>'+note()+
              '</measure><measure><barline location="left"><ending number="1" type="start"/></barline>'+note('D')+
              '<barline><ending number="1" type="stop"/><repeat direction="backward"/></barline></measure>'+
              '<measure><barline location="left"><ending number="2" type="start"/></barline>'+note('E')+
              '<barline><ending number="2" type="stop"/></barline></measure>')
        song=parse_musicxml(score(body))
        self.assertEqual([n.pitch for n in song.notes],[60,62,60,64])
        self.assertEqual([n.start for n in song.notes],[0,.5,1,1.5])
        changed=('<measure>'+note()+'</measure><measure><attributes><divisions>2</divisions></attributes>'+
                 '<direction><sound tempo="60"/></direction>'+note('D',2)+'<barline><repeat direction="backward"/></barline></measure>')
        song=parse_musicxml(score(changed))
        self.assertEqual([n.start for n in song.notes],[0,.5,1.5,2])
        self.assertAlmostEqual(song.seconds,3)

    def test_mxl_rmi_karaoke_and_standard_doctype(self):
        xml=(asset_dir()/'scores/twinkle.musicxml').read_bytes()
        container=b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="score.xml" media-type="application/vnd.recordare.musicxml+xml"/></rootfiles></container>'
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            z.writestr('META-INF/container.xml',container);z.writestr('score.xml',xml)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'score.mxl';path.write_bytes(data.getvalue())
            self.assertEqual(len(read_score(path).notes),42)
            midi=(asset_dir()/'scores/twinkle.mid').read_bytes()
            body=b'RMID'+b'data'+struct.pack('<I',len(midi))+midi+(b'\0' if len(midi)%2 else b'')
            path=Path(directory)/'score.rmi';path.write_bytes(b'RIFF'+struct.pack('<I',len(body))+body)
            self.assertEqual(len(read_score(path).notes),42)
            path=Path(directory)/'score.kar';path.write_bytes(midi)
            self.assertEqual(len(read_score(path).notes),42)
        standard=b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">'+score('<measure>'+note()+'</measure>')
        self.assertEqual(len(parse_musicxml(standard).notes),1)
        self.assertEqual(len(parse_musicxml(standard.decode().encode('utf-16')).notes),1)

    def test_untrusted_xml_and_archives_fail_closed(self):
        bad=b'<!DOCTYPE score-partwise [<!ENTITY x "abc">]>'+score('<measure>'+note()+'</measure>')
        for value in (bad,bad.decode().encode('utf-16'),b'<score-timewise/>'):
            with self.assertRaises(ValueError):parse_musicxml(value)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="../evil.xml"/></rootfiles></container>')
            z.writestr('../evil.xml',score('<measure>'+note()+'</measure>'))
        with self.assertRaises(ValueError):unpack_mxl(out.getvalue())
        with self.assertRaises(ValueError):parse_musicxml(score('<measure>'+note().replace('<step>C</step>','')+'</measure>'))
        with self.assertRaises(ValueError):parse_musicxml(score('<measure>'+note().replace('<step>C</step>','<step>C</step><alter>1e100000000</alter>')+'</measure>'))
        with self.assertRaisesRegex(ValueError,'拍号'):
            parse_musicxml(score('<measure><attributes><time><beats/><beat-type>4</beat-type></time></attributes>'+note()+'</measure>'))
        with self.assertRaisesRegex(ValueError,'小节内反复'):
            parse_musicxml(score('<measure>'+note()+'<barline location="middle"><repeat direction="backward"/></barline>'+note('D')+'</measure>'))


if __name__=='__main__':unittest.main()
