from opencc import OpenCC

_t2s = OpenCC('t2s')
_s2t = OpenCC('s2t')


def to_simplified(text: str) -> str:
    return _t2s.convert(text)


def to_traditional(text: str) -> str:
    return _s2t.convert(text)
