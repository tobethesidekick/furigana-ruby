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
    # food terms
    ('三文鱼', '鮭魚', True),
    ('金枪鱼', '鮪魚', True),
    ('吞拿鱼', '鮪魚', True),
    ('带鱼', '白帶魚', True),
    ('西兰花', '青花菜', True),
    ('花菜', '花椰菜', True),
    ('圆白菜', '高麗菜', True),
    ('卷心菜', '高麗菜', True),
    ('包菜', '高麗菜', True),
    ('小黄瓜', '小黃瓜', True),
    ('黄瓜', '小黃瓜', True),
    ('胡萝卜', '紅蘿蔔', True),
    ('西葫芦', '櫛瓜', True),
    ('红薯', '地瓜', True),
    ('猕猴桃', '奇異果', True),
    ('西柚', '葡萄柚', True),
    ('牛油果', '酪梨', True),
    ('鳄梨', '酪梨', True),
    ('圣女果', '小番茄', True),
    ('番石榴', '芭樂', True),
    ('车厘子', '櫻桃', True),
    ('橙子', '柳丁', True),
    ('芝士', '起司', True),
    ('黄油', '奶油', True),
    ('薯片', '洋芋片', True),
    ('三文治', '三明治', True),
    ('蛋挞', '蛋塔', True),
    ('比萨', '披薩', True),
    ('方便袋', '塑膠袋', True),
    ('小黄瓜和黄瓜', '小黃瓜和小黃瓜', True),   # no doubled 小
    ('烤红薯和红薯粉', '烤地瓜和地瓜粉', True),
    ('三文鱼片', '鮭魚片', True),
    ('马蹄糕', '馬蹄糕', True),     # deliberately not overridden
    ('提子', '提子', True),         # deliberately not overridden
    ('雪糕', '雪糕', True),         # creamy vs. 冰棒 not distinguishable
    ('黄瓜', '黃瓜', False),        # metadata: no overrides
    ('西红柿', '番茄', True),
    ('西红柿炒蛋', '番茄炒蛋', True),
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
