"""Public MIDI catalogs: searchable metadata, selected-file downloads only.

BitMidi publishes a sitemap index; its normal song pages publish downloadUrl.
Murashin's public uploader explicitly permits personal, low-load direct links.
No login, cookies, paywall workarounds, or execution of website JavaScript.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import io
import zipfile
import re
import threading
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
import xml.etree.ElementTree as ET

from .midi import convert, parse_midi

BITMIDI = "https://bitmidi.com"
MURASHIN = "https://murashin.sakura.ne.jp"
MUTOPIA = "https://www.mutopiaproject.org"
MUTOPIA_INDEX = MUTOPIA + "/datafiles/musiccache.dat"
PUBLIC_INDEX = MURASHIN + "/cgi-bin/upload.cgi?dir=&page=Main&sort=filename"
SOURCES = {"bitmidi": "BitMidi", "murashin": "动漫公开目录", "mutopia": "Mutopia 古典"}
MAX_MIDI_BYTES = 16 * 1024 * 1024
HEADERS = {"User-Agent": "NTE-MIDI-Desk/1.0 (personal MIDI catalog client)", "Accept-Encoding": "identity"}
PUNCTUATION = re.compile(r"[\W_]+", re.UNICODE)


class CatalogError(Exception):
    pass


class Cancelled(CatalogError):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled("操作已取消。")


def safe_url(url):
    try:
        parts = urlsplit(url)
        valid = (parts.scheme == "https" and parts.hostname in ("bitmidi.com", "murashin.sakura.ne.jp", "www.mutopiaproject.org", "mutopiaproject.org")
                 and not parts.username and not parts.password and parts.port in (None, 443))
    except ValueError:
        valid = False
    if not valid:
        raise CatalogError("来源地址不属于已支持的公开曲库。")
    return url


class CatalogRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch_bytes(url, limit, cancel=None, progress=None):
    # Public GETs are safe to repeat once when a connection times out. Keep
    # HTTP refusals and missing files visible instead of repeatedly requesting.
    for attempt in range(2):
        check_cancel(cancel)
        try:
            return _fetch_once(url, limit, cancel, progress)
        except CatalogError as error:
            transient = isinstance(error.__cause__, (URLError, TimeoutError, ConnectionError, OSError)) and not isinstance(error.__cause__, HTTPError)
            if attempt or not transient:
                raise
            if cancel is not None:
                cancel.wait(1)
            else:
                time.sleep(1)
    raise AssertionError("unreachable")


def _fetch_once(url, limit, cancel=None, progress=None):
    safe_url(url)
    check_cancel(cancel)
    try:
        request = Request(url, headers=HEADERS)
        with build_opener(CatalogRedirect()).open(request, timeout=15) as response:
            safe_url(response.url)
            length = response.headers.get("Content-Length", "")
            total = int(length) if length.isdigit() else 0
            if total > limit:
                raise CatalogError("来源文件过大，已停止下载。")
            chunks, received = [], 0
            while True:
                check_cancel(cancel)
                chunk = response.read(min(65536, limit + 1 - received))
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
                if received > limit:
                    raise CatalogError("来源文件超过大小限制，已停止下载。")
                if progress:
                    progress(received, total)
            check_cancel(cancel)
            return b"".join(chunks)
    except Cancelled:
        raise
    except HTTPError as error:
        if error.code in (401, 403):
            raise CatalogError("来源网站暂时拒绝直接访问，可稍后重试或打开来源网页。") from error
        if error.code == 404:
            raise CatalogError("这个版本的文件已下架，请换一个版本。") from error
        raise CatalogError(f"来源网站返回 HTTP {error.code}，请稍后重试。") from error
    except (URLError, TimeoutError, ConnectionError, OSError) as error:
        raise CatalogError("连接曲库失败或超时，请检查网络后重试。") from error


def normalized(text):
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()
    return PUNCTUATION.sub(" ", text).strip()


ALIAS_GROUPS = [
    ("三叶", "三叶主题曲", "三叶的主题曲", "三葉のテーマ", "Mitsuha", "Mitsuha Theme"),
    ("黄昏之时", "かたわれ時", "Kataware", "Katawaredoki", "Kataware Doki"),
    ("卡农", "Canon", "カノン"),
    ("千本樱", "千本桜", "Senbonzakura"),
    ("天空之城", "Laputa", "君をのせて", "Castle in the Sky"),
    ("小星星", "Twinkle", "きらきら星"),
    ("致爱丽丝", "Fur Elise", "Fuer Elise", "Für Elise", "エリーゼ"),
    ("青花瓷", "Qinghuaci", "Qing Hua Ci"),
    ("稻香", "Daoxiang", "Dao Xiang"),
    ("晴天", "Qingtian", "Qing Tian"),
    ("七里香", "Qilixiang", "Qi Li Xiang"),
    ("东京喰种", "东京食尸鬼", "Tokyo Ghoul", "Unravel"),
    ("贝多芬", "Beethoven"), ("莫扎特", "Mozart"), ("巴赫", "Bach"),
    ("肖邦", "Chopin"), ("李斯特", "Liszt"), ("舒伯特", "Schubert"),
    ("德彪西", "Debussy"), ("舒曼", "Schumann"), ("柴可夫斯基", "Tchaikovsky"),
    ("月光奏鸣曲", "Moonlight"), ("月光", "Clair de Lune", "Moonlight"),
    ("夜曲", "Nocturne"), ("土耳其进行曲", "Alla Turca", "Turkish March"),
    ("梦幻曲", "Traumerei"), ("爱之梦", "Liebestraum"),
    ("悲怆", "Pathetique"), ("钟", "La Campanella"),
    ("阿拉伯风格曲", "Arabesque"), ("平均律", "Well Tempered Clavier"),
    ("钢琴", "Piano"), ("练习曲", "Etude"), ("前奏曲", "Prelude"),
]


def query_variants(query):
    value = normalized(query)
    variants = [value]
    for group in ALIAS_GROUPS:
        group = [normalized(item) for item in group]
        if value in group:
            variants.extend(group)
    # Translate recognized Chinese terms inside combinations such as 肖邦 夜曲.
    expanded = [value]
    for group in sorted(ALIAS_GROUPS, key=lambda g: -max(map(len,g))):
        chinese = [normalized(s) for s in group if re.search(r"[\u4e00-\u9fff]",s)]
        english = [normalized(s) for s in group if s.isascii() and re.search(r"[a-zA-Z]",s)]
        if not english:
            continue
        for variant in list(expanded):
            for word in chinese:
                if word and word in variant:
                    for translation in english[:2]:
                        candidate = " ".join(variant.replace(word, " "+translation+" ").split())
                        if candidate not in expanded:
                            expanded.append(candidate)
                            if len(expanded) >= 24:
                                break
                if len(expanded) >= 24:break
            if len(expanded) >= 24:break
    variants.extend(expanded)
    return list(dict.fromkeys(variant for variant in variants if variant))


@dataclass(frozen=True)
class CatalogEntry:
    source: str
    key: str
    title: str
    size: int = 0
    composer: str = ""
    instrument: str = ""
    license: str = ""
    download_path: str = ""

    @property
    def page_url(self):
        if self.source == "bitmidi":
            return BITMIDI + "/" + quote(self.key, safe="-._~")
        if self.source == "mutopia":
            return MUTOPIA + "/cgibin/piece-info.cgi?id=" + self.key
        return MURASHIN + "/cgi-bin/adtunetr4mid.cgi?" + urlencode({"smf": "../upload/" + self.key})

    @property
    def search_text(self):
        return normalized(" ".join((self.title,self.key,self.composer,self.instrument,self.download_path)))


@dataclass
class SearchResult:
    entries: list[CatalogEntry]
    total: int
    catalog_count: int
    updated_at: str


@dataclass
class DownloadResult:
    path: Path
    title: str
    source: str
    page_url: str
    summary: dict


def validate_entry(entry):
    if entry.source not in SOURCES or not entry.key or len(entry.key) > 400:
        raise CatalogError("曲目来源无效。")
    if any(character in entry.key for character in ("/", "\\", "\x00")) or entry.key in (".", ".."):
        raise CatalogError("曲目地址格式无效。")
    if entry.source == "murashin" and not entry.key.casefold().endswith(".mid"):
        raise CatalogError("所选文件不是 MIDI。")
    if entry.source == "mutopia":
        path = PurePosixPath(entry.download_path)
        if (not entry.key.isdigit() or not entry.download_path.startswith("/ftp/")
                or ".." in path.parts or "\\" in entry.download_path or ":" in entry.download_path
                or path.suffix.lower() not in (".mid", ".midi", ".zip")
                or "?" in entry.download_path or "#" in entry.download_path or "\x00" in entry.download_path):
            raise CatalogError("Mutopia 曲目下载地址无效。")
    safe_url(entry.page_url)
    return entry


def parse_sitemap(data):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise CatalogError("曲库索引含有不支持的 XML 声明。")
    root = ET.fromstring(data)
    return [element.text.strip() for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "loc" and element.text]


def bitmidi_entries(urls):
    entries = []
    seen = set()
    for url in urls:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != "bitmidi.com" or parts.query or parts.fragment:
            continue
        key = unquote(parts.path.lstrip("/"))
        if not key or "/" in key or key in ("about", "privacy", "search", "random") or key in seen:
            continue
        seen.add(key)
        title = re.sub(r"-(?:mid|midi|kar)(-\d+)?$", lambda match: match.group(1) or "", key).replace("-", " ").title()
        entry = CatalogEntry("bitmidi", key, title)
        try:
            validate_entry(entry)
        except CatalogError:
            continue
        entries.append(entry)
    return entries


class RowParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells, self.cell, self.hrefs, self.rows = [], None, [], []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cells, self.hrefs, self.cell = [], [], None
        elif tag == "td":
            self.cell = []
        elif tag == "a":
            href = dict(attrs).get("href", "")
            if "adtunetr4mid.cgi?smf=" in href:
                self.hrefs.append(href)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.hrefs:
            self.rows.append((list(self.cells), self.hrefs[0]))


def murashin_entries(data):
    parser = RowParser()
    parser.feed(data.decode("euc-jp", "replace"))
    result, seen = [], set()
    for cells, href in parser.rows:
        if len(cells) < 5:
            continue
        value = parse_qs(urlsplit(href).query).get("smf", [""])[0]
        if not value.startswith("../upload/"):
            continue
        key = unquote(value[len("../upload/"):])
        if key in seen:
            continue
        description = re.sub(r"^\d+[.．]\s*", "", cells[2]).strip()
        title = Path(key).stem if description in ("", "なし", "無し", "no comment") else description
        title = {"056.Mitsuha.Thema.mid": "三叶的主题曲", "215.Katawaredoki.mid": "黄昏之时"}.get(key, title)
        title = title[:180]
        size = re.sub(r"[^0-9]", "", cells[4])
        entry = CatalogEntry("murashin", key, title, int(size) if size else 0)
        try:
            validate_entry(entry)
        except CatalogError:
            continue
        seen.add(key)
        result.append(entry)
    return result


def snapshot(source, entries):
    return {"schema": "nte-public-catalog-v1", "source": source,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": [[entry.key, entry.title, entry.size, {"composer":entry.composer,"instrument":entry.instrument,
                          "license":entry.license,"download_path":entry.download_path}] if entry.source == "mutopia"
                        else [entry.key, entry.title, entry.size] for entry in entries]}


def mutopia_entries(data):
    """Parse the public catalog used by the site's own listing CGI; no contacts."""
    entries, seen = [], set()
    for block in data.decode("utf-8-sig").replace("\r\n","\n").split("\n**********\n")[1:]:
        fields = block.splitlines()
        if len(fields) < 30 or fields[0] in seen:
            continue
        name = fields[4].strip()
        if not name.lower().endswith((".mid", ".midi", ".zip")):
            continue
        path = "/ftp/" + fields[1].strip().strip("/") + "/" + fields[2].strip().strip("/") + "/" + name
        title = " ".join(unescape(fields[12]+" "+fields[14]).split())[:180]
        entry = CatalogEntry("mutopia",fields[0],title,0,unescape(fields[13])[:120],
                             unescape(fields[16])[:120],unescape(fields[22])[:180],path)
        try:validate_entry(entry)
        except CatalogError:continue
        seen.add(entry.key);entries.append(entry)
    return entries


def write_snapshot(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
    temporary.replace(path)


def read_snapshot(path, source):
    path = Path(path)
    if path.stat().st_size > 12 * 1024 * 1024:
        raise CatalogError("本地曲库索引过大，请更新目录。")
    with gzip.open(path, "rb") as stream:
        data = stream.read(48 * 1024 * 1024 + 1)
    if len(data) > 48 * 1024 * 1024:
        raise CatalogError("曲库索引超过大小限制。")
    record = json.loads(data)
    if record.get("schema") != "nte-public-catalog-v1" or record.get("source") != source:
        raise CatalogError("曲库索引格式不兼容。")
    rows = record.get("entries")
    if not isinstance(rows, list) or len(rows) > 200000:
        raise CatalogError("曲库索引条目数量无效。")
    entries = []
    for row in rows:
        if not isinstance(row, list) or len(row) not in (3,4):
            continue
        key, title, size = row[:3]
        if not isinstance(key, str) or not isinstance(title, str) or not isinstance(size, int):
            continue
        extra = row[3] if len(row)==4 and isinstance(row[3],dict) else {}
        strings = [extra.get(k,"") for k in ("composer","instrument","license","download_path")]
        if not all(isinstance(s,str) and len(s)<=1024 for s in strings):continue
        entry = CatalogEntry(source, key, title[:180], max(0, size), *strings)
        try:
            validate_entry(entry)
            entries.append(entry)
        except CatalogError:
            pass
    if not entries:
        raise CatalogError("曲库索引为空，请更新目录。")
    return entries, str(record.get("updated_at", ""))


class CatalogClient:
    def __init__(self, directory, fetch=fetch_bytes, resources=None):
        self.directory, self.fetch = Path(directory), fetch
        self.resources = Path(resources) if resources is not None else self.directory
        self._catalogs, self._lock = {}, threading.RLock()

    def load(self, source):
        if source not in SOURCES:
            raise CatalogError("未知曲库来源。")
        with self._lock:
            if source in self._catalogs:
                return self._catalogs[source]
            paths = [self.directory / "catalog_cache" / f"{source}.json.gz",
                     self.resources / "catalogs" / f"{source}.json.gz"]
            for path in paths:
                try:
                    entries, updated_at = read_snapshot(path, source)
                    result = ([(entry, entry.search_text, normalized(entry.title)) for entry in entries], updated_at)
                    self._catalogs[source] = result
                    return result
                except (OSError, ValueError, CatalogError, EOFError):
                    continue
        raise CatalogError("本地曲库索引不可用，请点击“更新目录”。")

    def search(self, query, source="all", cancel=None, limit=100):
        query = query.strip()
        if len(query) < 2 or len(query) > 120:
            raise CatalogError("请输入 2–120 个字的曲名或关键词。")
        variants = [(value, value.split()) for value in query_variants(query)]
        sources = list(SOURCES) if source == "all" else [source]
        matches, count, dates = [], 0, []
        for provider in sources:
            rows, updated_at = self.load(provider)
            count += len(rows)
            dates.append(updated_at)
            for index, (entry, haystack, title_text) in enumerate(rows):
                if index % 500 == 0:
                    check_cancel(cancel)
                score = 0
                for variant, words in variants:
                    if variant == title_text:
                        score = max(score, 120)
                    elif variant in haystack:
                        score = max(score, 70 + min(30, len(variant)))
                    elif len(words) > 1 and all(word in haystack for word in words):
                        score = max(score, 35)
                if score:
                    if entry.source=="mutopia" and "piano" in normalized(entry.instrument):
                        score += 45
                    matches.append((score, entry))
        check_cancel(cancel)
        matches.sort(key=lambda pair: (-pair[0], len(pair[1].title), pair[1].title.casefold()))
        return SearchResult([entry for _, entry in matches[:limit]], len(matches), count, min(dates) if dates else "")

    def refresh(self, cancel=None, status=None):
        status = status or (lambda _: None)
        counts, failures = {}, []
        for source in SOURCES:
            check_cancel(cancel)
            try:
                if source == "bitmidi":
                    status("正在更新 BitMidi 公开目录…")
                    index = self.fetch(BITMIDI + "/sitemap.xml", 200000, cancel)
                    maps = parse_sitemap(index)
                    if not 1 <= len(maps) <= 8:
                        raise CatalogError("BitMidi 索引结构已变化，请稍后重试。")
                    urls = []
                    for number, url in enumerate(maps, 1):
                        if not re.fullmatch(r"https://bitmidi\.com/sitemap-\d+\.xml", url):
                            raise CatalogError("BitMidi 子目录地址无效。")
                        status(f"正在更新 BitMidi 目录 {number}/{len(maps)}…")
                        urls.extend(parse_sitemap(self.fetch(url, 12 * 1024 * 1024, cancel)))
                    entries = bitmidi_entries(urls)
                elif source == "murashin":
                    status("正在更新动漫公开目录…")
                    entries = murashin_entries(self.fetch(PUBLIC_INDEX, 16 * 1024 * 1024, cancel))
                else:
                    status("正在更新 Mutopia 古典目录…")
                    entries = mutopia_entries(self.fetch(MUTOPIA_INDEX, 8*1024*1024, cancel))
                if not entries:
                    raise CatalogError("来源返回的目录为空，已保留原有索引。")
                check_cancel(cancel)
                data = snapshot(source, entries)
                write_snapshot(self.directory / "catalog_cache" / f"{source}.json.gz", data)
                with self._lock:
                    self._catalogs[source] = ([(entry, entry.search_text, normalized(entry.title)) for entry in entries], data["updated_at"])
                counts[source] = len(entries)
            except Cancelled:
                raise
            except (CatalogError, ValueError, OSError, ET.ParseError) as error:
                failures.append(f"{SOURCES[source]}：{error}")
        if not counts:
            raise CatalogError("；".join(failures))
        return counts, failures

    def download(self, entry, cancel=None, status=None):
        validate_entry(entry)
        status = status or (lambda _: None)
        check_cancel(cancel)
        title = entry.title
        if entry.source == "bitmidi":
            status("正在读取曲目下载信息…")
            html = self.fetch(entry.page_url, 2 * 1024 * 1024, cancel).decode("utf-8", "replace")
            marker = re.search(r"window\.initStore\s*=\s*", html)
            if not marker:
                raise CatalogError("曲目网页暂时无法读取，请稍后重试或打开来源网页。")
            try:
                data = json.JSONDecoder().raw_decode(html[marker.end():])[0]
                item = data["data"]["midis"][entry.key]
                link = item["downloadUrl"]
                if item.get("slug") != entry.key or not re.fullmatch(r"/uploads/\d+\.mid", link):
                    raise ValueError("Unexpected MIDI link")
                url = BITMIDI + link
                if isinstance(item.get("name"), str):
                    title = re.sub(r"\.(?:mid|midi|kar)$", "", item["name"], flags=re.I)[:180]
            except (ValueError, TypeError, KeyError) as error:
                raise CatalogError("曲目网页结构已变化，请换一个版本或稍后重试。") from error
        elif entry.source == "murashin":
            url = MURASHIN + "/upload/" + quote(entry.key, safe="")
        else:
            url = MUTOPIA + quote(entry.download_path,safe="/._-~")
        status("正在下载 MIDI…")
        data = self.fetch(url, MAX_MIDI_BYTES, cancel)
        if entry.source == "mutopia" and entry.download_path.lower().endswith(".zip"):
            return self.download_archive(entry,data,cancel,status)
        return self.save_download(entry,data,title,cancel)

    def save_download(self,entry,data,title,cancel=None):
        if not data.startswith(b"MThd"):
            raise CatalogError("来源没有返回标准 MIDI 文件，请换一个版本。")
        song = parse_midi(data, title)
        summary = convert(song)["summary"]
        check_cancel(cancel)
        digest = hashlib.sha256(data).hexdigest()
        clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:65] or "MIDI"
        # Prefix avoids reserved DOS device names; content hash preserves versions.
        folder = self.directory / "downloaded_midis"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"midi_{clean}_{digest[:12]}.mid"
        temporary = path.with_suffix(".part")
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            temporary.write_bytes(data)
            check_cancel(cancel)
            temporary.replace(path)
        record = {"schema": "nte-downloaded-midi-v1", "title": title, "source": entry.source,
                  "page_url": entry.page_url, "sha256": digest, "filename": path.name,
                  "downloaded_at": datetime.now(timezone.utc).isoformat(), "summary": summary}
        if entry.source == "mutopia":
            record.update({"composer":entry.composer,"instrument":entry.instrument,"license":entry.license,
                           "download_url":MUTOPIA+quote(entry.download_path,safe="/._-~")})
        path.with_suffix(".source.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return DownloadResult(path, title, entry.source, entry.page_url, summary)

    def download_archive(self,entry,data,cancel,status):
        results = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos = archive.infolist()
                if len(infos)>256 or sum(i.file_size for i in infos)>32*1024*1024 or len({i.filename for i in infos})!=len(infos):
                    raise CatalogError("乐章 ZIP 展开过大或包含重复文件。")
                candidates = sorted((i for i in infos if PurePosixPath(i.filename).suffix.lower() in (".mid",".midi")),
                                    key=lambda i:re.sub(r"\d+",lambda m:m[0].zfill(6),i.filename.casefold()))
                if not 1<=len(candidates)<=64:
                    raise CatalogError("乐章 ZIP 中的 MIDI 数量无效。")
                for index,item in enumerate(candidates,1):
                    check_cancel(cancel)
                    path = PurePosixPath(item.filename)
                    if path.is_absolute() or ".." in path.parts or "\\" in item.filename or item.flag_bits&1 or item.file_size>MAX_MIDI_BYTES:
                        raise CatalogError("乐章 ZIP 的文件路径或大小无效。")
                    status(f"正在保存乐章 {index}/{len(candidates)}…")
                    with archive.open(item) as stream:value = stream.read(MAX_MIDI_BYTES+1)
                    if len(value)>MAX_MIDI_BYTES:raise CatalogError("乐章文件过大。")
                    results.append(self.save_download(entry,value,entry.title+" · "+path.stem,cancel))
        except (zipfile.BadZipFile,RuntimeError,OSError) as error:
            raise CatalogError("乐章 ZIP 无法读取。") from error
        return results

    def downloaded(self):
        folder = self.directory / "downloaded_midis"
        result = []
        for sidecar in folder.glob("*.source.json"):
            try:
                if sidecar.stat().st_size > 32768:
                    continue
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                filename = data.get("filename", "")
                if not isinstance(filename, str) or Path(filename).name != filename or "/" in filename or "\\" in filename:
                    continue
                path = folder / filename
                if data.get("schema") != "nte-downloaded-midi-v1" or not path.is_file():
                    continue
                if not isinstance(data.get("title"), str):
                    continue
                result.append((path, data))
            except (OSError, ValueError, TypeError):
                pass
        result.sort(key=lambda item: str(item[1].get("downloaded_at", "")), reverse=True)
        return result

    def title_for(self, path):
        path = Path(path).resolve()
        if path.parent != (self.directory / "downloaded_midis").resolve():
            return None
        try:
            sidecar = path.with_suffix(".source.json")
            if sidecar.stat().st_size > 32768:
                return None
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            title = data.get("title")
            return title[:180] if isinstance(title, str) else None
        except (OSError, ValueError, TypeError):
            return None
