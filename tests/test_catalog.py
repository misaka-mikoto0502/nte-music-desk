from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from nte_music_desk.catalog import CatalogClient,CatalogError,Cancelled,safe_url
import io
import zipfile
from nte_music_desk.paths import asset_dir


class CatalogChecks(unittest.TestCase):
    def test_search_offline_then_download_and_remember(self):
        requests=[]
        def fetch(url,limit,cancel=None,progress=None):
            requests.append(url)
            return (asset_dir()/"scores/twinkle.mid").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            client=CatalogClient(directory,fetch=fetch,resources=asset_dir())
            hits=client.search("黄昏之时")
            self.assertEqual(hits.catalog_count,122120)
            self.assertEqual(hits.entries[0].key,"215.Katawaredoki.mid")
            self.assertFalse(requests)
            result=client.download(hits.entries[0])
            self.assertEqual(len(requests),1)
            self.assertTrue(result.path.is_file())
            self.assertEqual(client.title_for(result.path),"黄昏之时")
            self.assertEqual(len(client.downloaded()),1)
            cancel=threading.Event();cancel.set()
            with self.assertRaises(Cancelled):client.download(hits.entries[0],cancel=cancel)

    def test_public_source_boundaries(self):
        for url in ("http://bitmidi.com/","https://localhost/","https://bitmidi.com.evil.test/","https://x:y@bitmidi.com/"):
            with self.assertRaises(CatalogError):safe_url(url)

    def test_classical_aliases_movement_zip_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            client=CatalogClient(directory,resources=asset_dir())
            self.assertEqual(client.search("致爱丽丝",source="mutopia").entries[0].key,"931")
            moon=client.search("贝多芬 月光",source="mutopia").entries[0]
            self.assertEqual(moon.key,"276")
            self.assertTrue(client.search("肖邦夜曲",source="mutopia").entries)
            self.assertTrue(client.search("巴赫前奏曲",source="mutopia").entries)
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as z:
                for filename in ('movement10.mid','movement2.mid','movement1.mid'):
                    z.writestr(filename,(asset_dir()/"scores/twinkle.mid").read_bytes())
            calls=[]
            def fetch(url,limit,cancel=None,progress=None):calls.append(url);return archive.getvalue()
            client.fetch=fetch
            results=client.download(moon)
            self.assertEqual(len(results),3)
            self.assertIn('movement1',results[0].title)
            self.assertIn('movement2',results[1].title)
            self.assertEqual(len(client.downloaded()),3)
            import json
            record=json.loads(results[0].path.with_suffix('.source.json').read_text(encoding='utf-8'))
            self.assertIn('Creative Commons',record['license'])
            self.assertIn('Beethoven',record['composer'])
            self.assertEqual(len(calls),1)


if __name__=="__main__": unittest.main()
