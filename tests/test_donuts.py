import pytest
from src.DoNuTS import DoseExtractor

class TestFixIso2022Jp:
    def test_normal_text(self):
        assert DoseExtractor.fix_iso2022jp_broken_text("Hello") == "Hello"
        assert DoseExtractor.fix_iso2022jp_broken_text("") == ""
        assert DoseExtractor.fix_iso2022jp_broken_text(None) is None

    def test_valid_iso2022jp(self):
        # 正常な ISO-2022-JP: "日本語"
        correct_text = "日本語"
        # ISO-2022-JP エンコードして、Latin-1 でデコードしたものを入力とする
        # pydicomがデコードせずにバイト列をLatin-1として文字列化した状態をシミュレート
        raw_bytes = correct_text.encode('iso-2022-jp')
        input_str = raw_bytes.decode('latin-1')
        assert DoseExtractor.fix_iso2022jp_broken_text(input_str) == correct_text

    def test_broken_aquilion_pattern_fukubu(self):
        # J"It -> 腹部 (42-02, 41-84 -> 4A 22, 49 74)
        # パターン: ESC $ B J " I t (ESC ( B 欠落)
        raw_bytes = b'\x1b$BJ"It' 
        input_str = raw_bytes.decode('latin-1')
        # 期待値: 腹部
        assert DoseExtractor.fix_iso2022jp_broken_text(input_str) == "腹部"

    def test_broken_aquilion_pattern_toubu(self):
        # F,It -> 頭部 (38-12, 41-84 -> 46 2C, 49 74)
        # パターン: ESC $ B F , I t
        raw_bytes = b'\x1b$BF,It'
        input_str = raw_bytes.decode('latin-1')
        assert DoseExtractor.fix_iso2022jp_broken_text(input_str) == "頭部"

    def test_mixed_ascii_missing_escape(self):
        # 腹部(単純) -> J"It(C1=c)
        # ESC $ B J " I t ( C 1 = c )
        # ( (0x28) が来た時点で ASCII に戻るべき
        raw_bytes = b'\x1b$BJ"It(C1=c)'
        input_str = raw_bytes.decode('latin-1')
        
        # C1=c -> 単純 (35-17: 43 31, 29-67: 3D 63)
        # ( と ) はASCII
        
        # 期待される挙動: J"It -> 腹部, ( -> ASCII, C1=c -> JIS(と判定されるか？), ) -> ASCII
        # 私の実装では:
        # JISモード中に '(' (0x28) が来たら ASCIIモードへ強制遷移。
        # その後 'C' (0x43) が来る。
        # ASCIIモード中に 'C' が来ても、それは 'C' (ASCII) として扱われる。
        # つまり "腹部(C1=c)" になってしまう可能性がある。
        
        # 待てよ、"C1=c" は JISコードだが、ESC $ B が直前にない。
        # 私の実装では「ASCIIモード中に唐突な $B」は検知するが、
        # 「ASCIIモード中に唐突なJIS文字」は検知できない（誤爆するため）。
        
        # しかし、実データでは "腹部(単純)" になっていた。
        # なぜか？
        # 実データには `(` の後に `\x1b$B` が入っていたのか？
        # debug_patch.py の出力: '\x1b$BJ"It(\x1b$BC1=c)'
        # ああ、実データには2回目の `\x1b$B` があったのだ！
        
        # テストデータもそれに合わせる
        raw_bytes = b'\x1b$BJ"It(\x1b$BC1=c)'
        input_str = raw_bytes.decode('latin-1')
        assert DoseExtractor.fix_iso2022jp_broken_text(input_str) == "腹部(単純)"

    def test_missing_esc_prefix(self):
        # ESC自体が欠落して $B から始まるケース
        # $B J " I t
        raw_bytes = b'$BJ"It'
        input_str = raw_bytes.decode('latin-1')
        assert DoseExtractor.fix_iso2022jp_broken_text(input_str) == "腹部"

