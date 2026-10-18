"""General MIDI voice metadata; one selectable part per track/channel/program."""
from collections import defaultdict
from dataclasses import replace

GM_NAMES = (
    'Acoustic Grand Piano|Bright Piano|Electric Grand Piano|Honky-tonk Piano|Electric Piano 1|Electric Piano 2|Harpsichord|Clavinet|'
    'Celesta|Glockenspiel|Music Box|Vibraphone|Marimba|Xylophone|Tubular Bells|Dulcimer|'
    'Drawbar Organ|Percussive Organ|Rock Organ|Church Organ|Reed Organ|Accordion|Harmonica|Tango Accordion|'
    'Nylon Guitar|Steel Guitar|Jazz Guitar|Clean Guitar|Muted Guitar|Overdriven Guitar|Distortion Guitar|Guitar Harmonics|'
    'Acoustic Bass|Finger Bass|Pick Bass|Fretless Bass|Slap Bass 1|Slap Bass 2|Synth Bass 1|Synth Bass 2|'
    'Violin|Viola|Cello|Contrabass|Tremolo Strings|Pizzicato Strings|Orchestral Harp|Timpani|'
    'String Ensemble 1|String Ensemble 2|Synth Strings 1|Synth Strings 2|Choir Aahs|Voice Oohs|Synth Voice|Orchestra Hit|'
    'Trumpet|Trombone|Tuba|Muted Trumpet|French Horn|Brass Section|Synth Brass 1|Synth Brass 2|'
    'Soprano Sax|Alto Sax|Tenor Sax|Baritone Sax|Oboe|English Horn|Bassoon|Clarinet|'
    'Piccolo|Flute|Recorder|Pan Flute|Blown Bottle|Shakuhachi|Whistle|Ocarina|'
    'Square Lead|Saw Lead|Calliope Lead|Chiff Lead|Charang Lead|Voice Lead|Fifths Lead|Bass + Lead|'
    'New Age Pad|Warm Pad|Polysynth Pad|Choir Pad|Bowed Pad|Metallic Pad|Halo Pad|Sweep Pad|'
    'Rain FX|Soundtrack FX|Crystal FX|Atmosphere FX|Brightness FX|Goblins FX|Echoes FX|Sci-fi FX|'
    'Sitar|Banjo|Shamisen|Koto|Kalimba|Bagpipe|Fiddle|Shanai|'
    'Tinkle Bell|Agogo|Steel Drums|Woodblock|Taiko Drum|Melodic Tom|Synth Drum|Reverse Cymbal|'
    'Guitar Fret Noise|Breath Noise|Seashore|Bird Tweet|Telephone|Helicopter|Applause|Gunshot'
).split('|')
FAMILIES = ('钢琴', '钟琴', '风琴', '吉他', '贝斯', '弦乐', '合奏', '铜管',
            '簧管', '笛管', '合成主音', '合成铺底', '音效', '民族乐器', '打击乐器', '环境音效')
ROLE_NAMES = {'melody': '主旋律', 'bass': '低音', 'harmony': '伴奏'}


def instrument_name(program, channel=0):
    return '打击乐 / Drum Kit' if channel == 9 else f'{FAMILIES[program // 8]} · {GM_NAMES[program]}'


def normalize_parts(song):
    """Stable virtual tracks; retain original physical track IDs for old presets."""
    if song.part_sources:
        return song
    groups = defaultdict(list)
    for n in song.notes:
        groups[n.track, n.channel, n.program].append(n)
    if len(groups) > 2048:
        raise ValueError('乐器声部超过 2048 个，请先精简曲谱。')
    names, notes, sources = [], [], {}
    for part, ((track, channel, program), original) in enumerate(sorted(groups.items())):
        names.append(song.track_names[track] if track < len(song.track_names) else f'轨道 {track + 1}')
        sources[part] = track
        notes.extend(replace(n, track=part) for n in original)
    notes.sort(key=lambda n: (n.start, n.track, n.pitch))
    return replace(song, notes=notes, track_names=names, part_sources=sources)


def role_hint(name, program, average):
    name = name.casefold()
    if any(word in name for word in ('melody', 'lead', '主题', '主旋律', 'vocal')):
        return 'melody'
    if any(word in name for word in ('bass', '低音')) or 32 <= program <= 39 or average < 50:
        return 'bass'
    return 'harmony'
