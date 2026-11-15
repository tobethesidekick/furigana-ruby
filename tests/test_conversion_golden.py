#!/usr/bin/env python3
"""Golden regression test for S→T (s2twp) conversion.

Run after every OpenCC data refresh or guard change:
  OPENCC_PATH=/tmp/oc_new python3 tests/test_conversion_golden.py [novel.txt]

Each GOLDEN row is (simplified, expected traditional, chapter_text?). Optional
novel.txt (not stored in the repo — copyrighted) is converted and the output
saved to <novel>.s2twp.out; diff it between runs to review data-refresh changes.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if os.environ.get('OPENCC_PATH'):
    sys.path.insert(0, os.environ['OPENCC_PATH'])
spec = importlib.util.spec_from_file_location(
    'chinese_engine', os.path.join(HERE, '..', 'chinese_engine.py'))
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)

GOLDEN = [
    # Taiwan-usage overrides (chapter text)
    ('数字专辑发布', '數位專輯釋出', True),
    ('点赞和外卖', '按讚和外送', True),
    ('举报他', '檢舉他', True),       # _TW_CUSTOM_PHRASES (both Taiwan variants)
    ('举报他', '檢舉他', False),      # ...applies to metadata too
    # guards
    ('他一出事就跑了', '他一出事就跑了', True),
    ('一出门就下雨', '一出門就下雨', True),
    ('只剩一个', '只剩一個', True),
    ('的士兵走了', '的士兵走了', True),
    ('乍得回过神', '乍得回過神', True),
    ('天蚕土豆写的', '天蠶土豆寫的', True),
    # scope: metadata must NOT get overrides (author pen name stays a name)
    ('天蚕土豆', '天蠶土豆', False),
    ('土豆', '土豆', False),
]


def main():
    conv = ce._get_converter('s2twp')
    fails = 0
    for src, want, chapter in GOLDEN:
        got = ce._convert_text(src, conv, overrides=chapter)
        if got != want:
            fails += 1
            print('FAIL %r: want %r got %r' % (src, want, got))
    print('%d/%d golden cases passed' % (len(GOLDEN) - fails, len(GOLDEN)))
    if len(sys.argv) > 1:
        out = sys.argv[1] + '.s2twp.out'
        with open(sys.argv[1], encoding='utf-8') as f, \
                open(out, 'w', encoding='utf-8') as o:
            for line in f:
                o.write(ce._convert_text(line, conv, overrides=True))
        print('wrote', out)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
