"""
DoNuTS (Dose Counter for Nuclear Medicine and CT Systems)

RDSR (Radiation Dose Structured Report) と DICOM ヘッダーから
線量情報と患者情報を抽出し、CSV形式で出力するオープンソースソフトウェア。

Author: Sugimoto Kohei
Date: 2026-02-04
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import os
import warnings
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Generator, Iterable, List, Optional, Set

import pydicom
from pydicom.dataset import FileDataset
from pydicom.errors import InvalidDicomError
from tqdm import tqdm

# -----------------------------------------------------------------------------
# Logging & Warnings
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Suppress annoying pydicom warnings
warnings.filterwarnings("ignore", message=".*Failed to decode byte string.*")
warnings.filterwarnings("ignore", message=".*Unknown encoding.*")
warnings.filterwarnings("ignore", message=".*Found unknown escape sequence.*")
# pydicom's own logger might duplicate warnings, so we silence it specifically
logging.getLogger("pydicom").setLevel(logging.ERROR)

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
RDSR_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.88.67"  # X-Ray Radiation Dose SR Storage


CODES: Dict[str, str] = {
    "CTAcquisition": "113819",
    "TotalNumberofIrradiationEvents": "113812",
    "CTDoseLengthProductTotal": "113813",
}

RDSR_COLUMNS: Dict[str, str] = {
    "MeanCTDIvol": "113830",
    "DLP": "113838",
    "Comment": "121106",
    "XRayModulationType": "113842",
    "CTDIwPhantomType": "113835",
    "AcquisitionProtocol": "125203",
    "TargetRegion": "123014",
    "CTAcquisitionType": "113820",
    "ProcedureContext": "G-C32C",
    "ExposureTime": "113824",
    "ScanningLength": "113825",
    "ExposedRange": "113899",
    "NominalSingleCollimationWidth": "113826",
    "NominalTotalCollimationWidth": "113827",
    "PitchFactor": "113828",
    "IdentificationoftheXRaySource": "113832",
    "KVP": "113733",
    "MaximumXRayTubeCurrent": "113833",
    "MeanXRayTubeCurrent": "113734",
    "ExposureTimeperRotation": "113834",
    "DeviceManufacturer": "113878",
    "DeviceSerialNumber": "113880",
    "DeviceObserverManufacturer": "121014",
    "DeviceObserverModelName": "121015",
    "DLPNotificationValue": "113911",
    "CTDIvolNotificationValue": "113912",
    "ReasonforProceeding": "113907",
}

# code -> column 逆引き
RDSR_CODE_TO_COLUMN: Dict[str, str] = {code: col for col, code in RDSR_COLUMNS.items()}

RDSR_HEADER_COLUMNS = [
    "ManufacturerModelName",
    "PatientID",
    "StudyDate",
    "PatientName",
    "StudyDescription",
    "PatientBirthDate",
    "PatientSex",
    "PatientAge",
    "PatientSize",
    "PatientWeight",
]

PET_COLUMNS = ["PatientID", "StudyDate", "RadionuclideTotalDose"]

# 出力CSVのカラム順序（見やすさのため）
OUTPUT_FIELD_ORDER = (
    RDSR_HEADER_COLUMNS
    + list(RDSR_COLUMNS.keys())
    + ["CTDoseLengthProductTotal"]
    + ["RadionuclideTotalDose"]
)


# -----------------------------------------------------------------------------
# Small utilities
# -----------------------------------------------------------------------------
def safe_str(getter: Any, default: str = "") -> str:
    """pydicom値を安全に str 化（Noneや未定義に強くする）。"""
    if getter is None:
        return default
    try:
        return str(getter)
    except Exception:
        return default


def is_pet_original(ds: FileDataset) -> bool:
    """PET画像っぽいものを安全に判定する。"""
    modality = getattr(ds, "Modality", None)
    if modality != "PT":
        return False

    image_type = getattr(ds, "ImageType", None)
    if not image_type:
        return False

    # pydicom MultiValue (v3.0+) might not be an instance of list
    try:
        return "ORIGINAL" in image_type
    except Exception:
        return False


def iter_file_paths(root: str) -> Iterable[str]:
    """ディレクトリ配下の全ファイルパスを列挙。"""
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            yield os.path.join(dirpath, fn)


# -----------------------------------------------------------------------------
# Main extractor
# -----------------------------------------------------------------------------
@dataclass
class DoseExtractor:
    input_dir: str

    def __post_init__(self) -> None:
        self.rdsr_rows: List[Dict[str, Any]] = []
        self.pet_rows: List[Dict[str, Any]] = []

    # ---- text fix ------------------------------------------------------------
    @staticmethod
    def fix_iso2022jp_broken_text(text: Optional[str]) -> Optional[str]:
        """ISO-2022-JPのエスケープ欠落等を修復する。"""
        if not isinstance(text, str):
            return text

        if not ("\x1b" in text or "$B" in text):
            return text

        try:
            raw = text.encode("latin-1")
        except UnicodeEncodeError:
            return text

        decoded_chars: List[str] = []
        i = 0
        length = len(raw)
        mode = "ASCII"  # 'ASCII' or 'JIS'

        while i < length:
            b1 = raw[i]

            # ESC sequence
            if b1 == 0x1B:
                if i + 2 < length:
                    seq = raw[i : i + 3]
                    if seq in (b"\x1b$B", b"\x1b$@"):
                        mode = "JIS"
                        i += 3
                        continue
                    if seq in (b"\x1b(B", b"\x1b(J"):
                        mode = "ASCII"
                        i += 3
                        continue
                i += 1
                continue

            if mode == "ASCII":
                # '$B' without ESC
                if b1 == 0x24 and i + 1 < length and raw[i + 1] == 0x42:
                    mode = "JIS"
                    i += 2
                    continue
                decoded_chars.append(chr(b1))
                i += 1
                continue

            # JIS mode
            if not (0x21 <= b1 <= 0x7E) or i + 1 >= length:
                mode = "ASCII"
                continue

            b2 = raw[i + 1]

            # heuristic suspicious bytes
            if b1 in (0x28, 0x29, 0x2C, 0x2E):  # (,),,.
                mode = "ASCII"
                continue

            try:
                euc_bytes = bytes([b1 | 0x80, b2 | 0x80])
                decoded_chars.append(euc_bytes.decode("euc-jp"))
                i += 2
            except Exception:
                mode = "ASCII"

        return "".join(decoded_chars)

    # ---- DICOM IO ------------------------------------------------------------
    def iter_dicom_datasets(self) -> Generator[FileDataset, None, None]:
        paths = list(iter_file_paths(self.input_dir))
        for p in tqdm(paths, desc="ファイルを探索中"):
            try:
                ds = pydicom.dcmread(p, stop_before_pixels=True)
                yield ds
            except (InvalidDicomError, TypeError):
                continue
            except Exception as e:
                logger.debug("Skipping file %s: %s", p, e)

    # ---- Public API ----------------------------------------------------------
    def process(self) -> List[Dict[str, Any]]:
        for ds in self.iter_dicom_datasets():
            try:
                if getattr(ds, "SOPClassUID", None) == RDSR_SOP_CLASS_UID:
                    self.process_rdsr(ds)
                elif is_pet_original(ds):
                    self.process_pet(ds)
            except Exception as e:
                logger.error("Error processing dataset: %s", e)

        # PETデータの重複排除 (PatientID, StudyDate, Doseが同じもの)
        unique_pet_rows = []
        seen_pet = set()
        for row in self.pet_rows:
            # 辞書はハッシュ化できないのでタプルにして判定
            key = (row.get("PatientID"), row.get("StudyDate"), row.get("RadionuclideTotalDose"))
            if key not in seen_pet:
                seen_pet.add(key)
                unique_pet_rows.append(row)
        
        self.pet_rows = unique_pet_rows

        if not self.rdsr_rows and not self.pet_rows:
            return []

        if not self.rdsr_rows:
            return self.pet_rows
        
        if not self.pet_rows:
            return self.rdsr_rows

        # データの結合 (Merge)
        # キー: (PatientID, StudyDate)
        # RDSRデータをベースに、一致するPETデータがあれば情報を付加する
        # SQLの FULL OUTER JOIN 相当を実装するのは複雑なので、
        # ここでは RDSR に PET を LEFT JOIN する形 + PETのみの行を追加する簡易実装とする
        # （要件的に、CT線量レポートとPET線量情報の突合が主目的と想定）
        
        # PETデータをキーでインデックス化 (重複がある場合は最初の一つを採用、あるいはリスト化？)
        # 簡易的に最初の一つを採用する
        pet_map = {}
        for p_row in self.pet_rows:
            pid = p_row.get("PatientID", "")
            sdate = p_row.get("StudyDate", "")
            if pid and sdate:
                pet_map[(pid, sdate)] = p_row.get("RadionuclideTotalDose", "")

        merged_rows = []
        
        # 1. RDSRベースの結合
        matched_pet_keys = set()
        for r_row in self.rdsr_rows:
            new_row = r_row.copy()
            pid = r_row.get("PatientID", "")
            sdate = r_row.get("StudyDate", "")
            key = (pid, sdate)
            
            if key in pet_map:
                new_row["RadionuclideTotalDose"] = pet_map[key]
                matched_pet_keys.add(key)
            else:
                new_row["RadionuclideTotalDose"] = ""
            merged_rows.append(new_row)
            
        # 2. マッチしなかったPETデータを追加（RDSRがない検査）
        for p_row in self.pet_rows:
            pid = p_row.get("PatientID", "")
            sdate = p_row.get("StudyDate", "")
            key = (pid, sdate)
            
            if key not in matched_pet_keys:
                # RDSRのカラムは空で埋める
                new_row = {col: "" for col in OUTPUT_FIELD_ORDER}
                new_row.update(p_row) # PatientID, StudyDate, Doseを上書き
                merged_rows.append(new_row)

        return merged_rows

    # ---- RDSR ----------------------------------------------------------------
    def process_rdsr(self, ds: FileDataset) -> None:
        content = getattr(ds, "ContentSequence", None)
        if not content:
            return

        events_val = self._find_value_flat(content, CODES["TotalNumberofIrradiationEvents"])
        try:
            events = int(events_val) if events_val is not None else 0
        except Exception:
            events = 0

        cdlpt_val = self._find_value_flat(content, CODES["CTDoseLengthProductTotal"])
        cdlpt = "" if cdlpt_val is None else cdlpt_val

        header_info: Dict[str, Any] = {col: safe_str(getattr(ds, col, "")) for col in RDSR_HEADER_COLUMNS}

        common_data = self._extract_common_data_flat(content)
        common_data = {k: self.fix_iso2022jp_broken_text(v) for k, v in common_data.items()}

        ct_acquisitions = [item for item in content if self._has_code(item, CODES["CTAcquisition"])]

        if not ct_acquisitions:
            if events > 0:
                for _ in range(events):
                    row = dict(header_info)
                    row.update(common_data)
                    row["CTDoseLengthProductTotal"] = cdlpt
                    self.rdsr_rows.append(row)
            return

        for acq in ct_acquisitions:
            row = dict(header_info)
            row.update(common_data)
            row["CTDoseLengthProductTotal"] = cdlpt

            acq_data: Dict[str, Any] = {}
            self._extract_values_recursive(acq, acq_data)

            for k, v in list(acq_data.items()):
                acq_data[k] = self.fix_iso2022jp_broken_text(v)

            row.update(acq_data)
            self.rdsr_rows.append(row)

    def _extract_common_data_flat(self, sequence: Iterable[Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for item in sequence:
            code = self._get_code_value(item)
            if not code:
                continue
            col = RDSR_CODE_TO_COLUMN.get(code)
            if not col:
                continue
            val = self._get_item_value(item)
            if val is not None:
                out[col] = val
        return out

    # ---- PET -----------------------------------------------------------------
    def process_pet(self, ds: FileDataset) -> None:
        row: Dict[str, Any] = {
            "PatientID": safe_str(getattr(ds, "PatientID", "")),
            "StudyDate": safe_str(getattr(ds, "StudyDate", "")),
            "RadionuclideTotalDose": "",
        }

        seq = getattr(ds, "RadiopharmaceuticalInformationSequence", None)
        if seq and len(seq) > 0:
            first = seq[0]
            val = getattr(first, "RadionuclideTotalDose", None)
            if val is not None:
                row["RadionuclideTotalDose"] = val

        self.pet_rows.append(row)

    # ---- DICOM SR helpers ----------------------------------------------------
    def _get_code_value(self, item: Any) -> Optional[str]:
        cseq = getattr(item, "ConceptNameCodeSequence", None)
        if not cseq:
            return None
        try:
            return cseq[0].CodeValue
        except Exception:
            return None

    def _has_code(self, item: Any, target_code: str) -> bool:
        return self._get_code_value(item) == target_code

    def _find_value_flat(self, sequence: Iterable[Any], target_code: str) -> Optional[Any]:
        for item in sequence:
            if self._has_code(item, target_code):
                return self._get_item_value(item)
        return None

    def _extract_values_recursive(self, container: Any, out: Dict[str, Any]) -> None:
        stack = [container]
        while stack:
            node = stack.pop()
            seq = getattr(node, "ContentSequence", None)
            if not seq:
                continue

            for item in seq:
                code = self._get_code_value(item)
                if code:
                    col = RDSR_CODE_TO_COLUMN.get(code)
                    if col:
                        val = self._get_item_value(item)
                        if val is not None:
                            out[col] = val

                if getattr(item, "ContentSequence", None):
                    stack.append(item)

    def _get_item_value(self, item: Any) -> Optional[Any]:
        if hasattr(item, "TextValue"):
            return item.TextValue
        if hasattr(item, "NumericValue"):
            return item.NumericValue
        if hasattr(item, "MeasuredValueSequence"):
            try:
                return item.MeasuredValueSequence[0].NumericValue
            except Exception:
                return None
        if hasattr(item, "ConceptCodeSequence"):
            try:
                return item.ConceptCodeSequence[0].CodeMeaning
            except Exception:
                return None
        if hasattr(item, "PersonName"):
            return safe_str(item.PersonName)
        if hasattr(item, "UID"):
            return safe_str(item.UID)
        return None


# -----------------------------------------------------------------------------
# Output
# -----------------------------------------------------------------------------
def write_csv_no_pandas(data: List[Dict[str, Any]], output_dir: str) -> str:
    """pandasを使わずにCSV出力を行う。"""
    date_str = dt.date.today().isoformat()
    out_path = os.path.join(output_dir, f"{date_str}.csv")
    
    # 書き込み対象の全カラム（フィールド）を確定
    # 基本は OUTPUT_FIELD_ORDER だが、データ内に未知のキーがあれば追加する（念のため）
    fieldnames = list(OUTPUT_FIELD_ORDER)
    
    # データを整形（Noneを空文字に、数値を文字列に）
    # かつ、fieldnamesに含まれないキーがあれば無視するか、fieldnamesに追加するか。
    # ここでは無視せず、定義済みのものだけ出力する方針とする（順序保証のため）
    
    # 書き込み実行
    # encoding='cp932', errors='replace' で書き込む
    try:
        with open(out_path, 'w', encoding='cp932', errors='replace', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)
        return out_path
    except Exception as e:
        logger.warning("保存エラー (cp932): %s", e)
        out_path_utf8 = os.path.join(output_dir, f"{date_str}_utf8.csv")
        with open(out_path_utf8, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)
        return out_path_utf8


# -----------------------------------------------------------------------------
# GUI directory picker (optional)
# -----------------------------------------------------------------------------
def select_directory(initial_path: str) -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        return filedialog.askdirectory(initialdir=initial_path, title="DICOMフォルダを選択")
    finally:
        root.destroy()


def show_done_message(path: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("処理完了", f"{path} にデータが保存されました")
        root.destroy()
    except Exception:
        pass


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract CT RDSR and PET dose info and export CSV.")
    p.add_argument("target_dir", nargs="?", default="", help="DICOM root directory (if omitted, GUI picker is used)")
    p.add_argument("--no-gui", action="store_true", help="Disable GUI even if target_dir is omitted")
    p.add_argument("--debug", action="store_true", help="Enable debug logging")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    target_dir = args.target_dir

    if not target_dir:
        if args.no_gui:
            raise SystemExit("target_dir が未指定です。引数でディレクトリを指定してください。")
        initial = os.path.join(os.path.expanduser("~"), "Desktop")
        target_dir = select_directory(initial)

    if not target_dir:
        raise SystemExit("フォルダが選択されませんでした。")

    print(f"処理対象: {target_dir}")

    extractor = DoseExtractor(target_dir)
    result_data = extractor.process()

    if not result_data:
        print("有効なデータが見つかりませんでした。")
        return

    saved_path = write_csv_no_pandas(result_data, target_dir)
    print(f"保存完了: {saved_path}")

    # GUI経由のときだけ完了ダイアログ
    if not args.no_gui and not args.target_dir:
        show_done_message(target_dir)


if __name__ == "__main__":
    main()