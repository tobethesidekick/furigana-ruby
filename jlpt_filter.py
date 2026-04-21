"""
jlpt_filter.py  v3
Granular per-level JLPT filtering.
Caller passes a set of levels to ANNOTATE (e.g. {'N1','N2','N3'}).
"""

# ── JLPT kanji by level ───────────────────────────────────────────────────────
# Each set contains kanji first appearing at that level.

JLPT_N5_KANJI = set(
    "日一国会人年大十二本中長出三時行見月分後前生五間上東四今金九入学高円子外"
    "八六下来気小七山話女北午百書先名川千水半男西電校語土木聞食車何南万毎白"
    "天母火右読友左休父雨"
)

JLPT_N4_KANJI = set(
    "犬牛馬魚鳥花草木林森海池川湖山野原田畑空雲雨雪風晴曇星月夜朝昼夕暑寒春"
    "夏秋冬週末曜早起寝待歩走乗降借貸返払買売送受取持運転歌飲食作洗料理服着"
    "帽靴荷旅写真映画音楽新聞雑誌手紙電話世界国語英数科算体育美術工道徳社理"
    "歴地政経文化生活習慣伝統結婚離子供親兄弟姉妹達先生医者警察消防銀行郵便"
    "図書館病院学校会社工場農店台公園広場駅港空橋道路信号角進渡地下鉄船自転"
    "開始使方式切近思明暗重軽同事仕度強公保知死区物病"
)

JLPT_N3_KANJI = set(
    "悪安暗医委意育員院飲運泳駅央横屋温化荷界開階感漢館岸起期客究急級宮球去"
    "橋業曲局近銀区苦具係軽血決研県庫湖向幸港号根祭坂皿指歯詩持式実写者守酒"
    "受州終習集住重宿所暑助勝商昭消植申身神真深整昔全相息速族打対待第炭短談"
    "着注柱帳調追定庭笛鉄転都投島湯登等動童農波配倍箱坂板悲皮美鼻筆氷表秒品"
    "負部服福平返勉報放味無面役薬由遊予洋葉陽落流旅両緑礼列練路和"
)

JLPT_N2_KANJI = set(
    "握扱依偉違維慰緯壱逸茨芋鋳姻陰韻渦浦影鋭液疫悦謁越閲宴援煙猿縁艶汚凹"
    "奥憶臆虞乙卸恩穏佳嫁寡暇架禍稼箇華菓貨蚊隠戒拡核獲穫鶴括渇滑褐缶陥含"
    "頑企奇岐幾忌既棋棄棋欺欺殊寛肝韓甘玩机陶叫驚凝斤謹緊禽薫茎傑欠訣絹謙"
    "懸顕孤弧枯呼誇壱鋼巧拘控更拷貢購溝綱酷獄込墾魂恨懇佐詐鎖砕索錯刷惨暫"
    "繁伐髪抜扶含柄弊癖璧偏捕募慕朴没奔翻摩魔磨麻繭慢漫魅妙矛霧冥盟滅免茂"
    "模網紋厄躍柳愉癒裕融雄抑羅雷頼欄濫吏履痢硫隆虜慮了僚寮療糧倫隣塁累励"
    "霊鈴隷零廉恋錬炉露廊楼浪漏郎湾腕"
)

JLPT_N1_KANJI = set(
    "唖挨曖宛嬉俺臆苛牙崖骸葛鎌巌毀畿臼串窟薫詣倦鍵膠拷梗喉乞昏痕恣餌嫌赦"
    "煮遮釈爵拾愁呪袖渋塾峻醇庶哨宵娼宴憧拭瘦汰朕黛嗅淡坦痴逐捗喋貼諦泥溺"
    "瞳曇苗畏賦憤塞拙噌璃穿箋膳狙遡曹喪槽漕踪踏遁豚那虹廿捻把把覇肌罰伐氾"
    "藩汎膚訃払沸噴憤塞蔽壁弊癖貌飽慕俸帽縫亡乏紡肪某冒剖傍妨房坊朋訪膨謀"
    "墨撲没翻磨魔抹慢漫蜜妄耗悶匁冶鎔洛辣嵐欄吏痢硫慮僚寮糧倫厘塁励零廉錬"
)

# Build lookup: kanji char → level string
_KANJI_LEVEL = {}
for _k in JLPT_N5_KANJI: _KANJI_LEVEL[_k] = 'N5'
for _k in JLPT_N4_KANJI: _KANJI_LEVEL[_k] = 'N4'
for _k in JLPT_N3_KANJI: _KANJI_LEVEL[_k] = 'N3'
for _k in JLPT_N2_KANJI: _KANJI_LEVEL[_k] = 'N2'
for _k in JLPT_N1_KANJI: _KANJI_LEVEL[_k] = 'N1'
# Anything not in any list = unlisted / non-JLPT → treat as 'N1' (hardest)


def is_kanji(char):
    cp = ord(char)
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0xF900 <= cp <= 0xFAFF)


def get_kanji_level(char):
    """Return JLPT level string for a kanji, or 'N1' if unlisted.
    Unlisted chars are treated as N1 for annotation purposes (hardest)."""
    return _KANJI_LEVEL.get(char, 'N1')


def get_kanji_level_exact(char):
    """Return JLPT level string for a kanji, or 'unlisted' if not in any list.
    Use this for detection/reporting — preserves the unlisted distinction."""
    return _KANJI_LEVEL.get(char, 'unlisted')


def word_needs_annotation(word, annotate_levels=None):
    """
    Return True if this word should receive furigana.

    annotate_levels: set of level strings to annotate, e.g. {'N1','N2','N3'}
                     None = annotate everything
                     empty set = annotate nothing

    Rules:
      - No kanji → False
      - annotate_levels is None → always True (annotate all)
      - Multi-kanji compound → True if ANY kanji char's level is in annotate_levels
      - Single kanji → True only if its level is in annotate_levels
    """
    kanji_chars = [c for c in word if is_kanji(c)]
    if not kanji_chars:
        return False
    if annotate_levels is None:
        return True
    if not annotate_levels:
        return False
    # For any kanji in the word, check if its level is selected
    return any(get_kanji_level(c) in annotate_levels for c in kanji_chars)


# ── Default level sets ────────────────────────────────────────────────────────

LEVELS_ALL       = {'N1', 'N2', 'N3', 'N4', 'N5'}
LEVELS_N1_N3     = {'N1', 'N2', 'N3'}
LEVELS_N1_N4     = {'N1', 'N2', 'N3', 'N4'}
LEVELS_NONE      = set()
