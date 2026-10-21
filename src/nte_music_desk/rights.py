"""Explicit user statements and model terms, never an automated legal verdict."""
MUSCRIPTOR_TERMS = 'muscriptor-cc-by-nc-4.0-2026-10-21'
GAME_TERMS = 'game-1.0-cc-by-nc-sa-4.0-2026-10-21'
MODEL_TERMS = {
    MUSCRIPTOR_TERMS: {'name': 'MuScriptor', 'license': 'CC BY-NC 4.0 + additional conditions',
                       'url': 'https://huggingface.co/MuScriptor/muscriptor-medium'},
    GAME_TERMS: {'name': 'GAME', 'license': 'CC BY-NC-SA 4.0',
                'url': 'https://github.com/openvpi/GAME/releases/tag/v1.0.0'},
}
SOURCE_BASES = {
    'original': '自有原创作品及录音',
    'permission': '已获此次转谱所需的授权',
    'open-license': '开放许可覆盖此次使用',
    'public-domain-recording': '作品及录音均可合法用于此次处理',
}


def validate_use(basis, reference, accepted_models, models):
    if not isinstance(basis, str) or basis not in SOURCE_BASES:
        raise ValueError('请选择输入素材的使用依据；文件在本机或可免费下载不代表具备转谱授权。')
    if not isinstance(reference, str) or not 1 <= len(reference.strip()) <= 2000:
        raise ValueError('请填写来源 / 授权依据，例如原创录音说明、许可链接或授权记录（不超过 2000 字）。')
    if not isinstance(accepted_models, tuple) or any(not isinstance(m, str) or m not in MODEL_TERMS for m in accepted_models):
        raise ValueError('模型许可记录无效。')
    missing = [MODEL_TERMS[m]['name'] for m in models if m not in accepted_models]
    if missing:
        raise ValueError('请先阅读并确认所选模型条款及非商业使用限制：' + '、'.join(missing) + '。')
    return {'basis': basis, 'reference': reference.strip(), 'status': 'user_statement_not_verified',
            'model_terms': {m: MODEL_TERMS[m] for m in models},
            'publication_rights': 'not_verified; check separately before sharing MIDI or video'}


def require_separation_license():
    # The publicly downloadable ViperX checkpoint has no verified grant in our
    # audit. Wrapper code's MIT license cannot license those third-party weights.
    raise ValueError('原唱分离暂不可用：原分离模型的权重许可尚未核实，已停用下载与调用。请使用已获授权的伴奏 / 纯音乐，或单独试用主旋律 Beta。')
