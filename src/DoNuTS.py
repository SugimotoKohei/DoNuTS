import os
import sys
import glob
import datetime
from tqdm import tqdm
import tkinter
from tkinter import filedialog
from tkinter import messagebox

import pydicom
import pandas as pd

# RDSRのSOP Class UID (X-Ray Radiation Dose SR)
RDSR_SOP_CLASS_UID = '1.2.840.10008.5.1.4.1.1.88.67'

# SRのツリーを辿る際に、項目が存在しない場合に発生する例外
MISSING_ERRORS = (KeyError, IndexError, TypeError, AttributeError)


def select_directory(initial_path):
    '''tkinterのGUIでDICOMが入ったディレクトリを指定させて、そのディレクトリのパスを出力'''
    tk = tkinter.Tk()
    tk.withdraw()
    dicom_directory = filedialog.askdirectory(
        initialdir=initial_path, title='DICOMファイルが含まれるフォルダを選択')
    return dicom_directory


def get_file_path(directory):
    '''ディレクトリを入力し、ディレクトリ内のファイルのパスをすべて出力'''
    if directory == '':
        sys.exit(0)
    path_of_files = glob.glob(directory + '/**/*', recursive=True)
    return [p for p in path_of_files if os.path.isfile(p)]


def get_dicom_path(path):
    '''パスを入力し、その中のDICOMだけを出力（画像データは読み込まない）'''
    dicom_files = []
    skipped = 0
    for p in tqdm(path, desc='データを読み込み中'):
        try:
            dicom_files.append(pydicom.dcmread(p, stop_before_pixels=True))
        except Exception:
            skipped += 1
    if skipped:
        print(f'DICOMとして読み込めなかったファイル: {skipped}件')
    return dicom_files


def separate_dicom_files(dicom_files):
    '''DICOMファイルを入力し、RDSRとPETに分割してそれぞれをタプルで出力'''
    rdsr_files = []
    pet_files = []

    for f in tqdm(dicom_files, desc='データを分割中'):
        image_type = getattr(f, 'ImageType', None) or ['']
        if getattr(f, 'SOPClassUID', None) == RDSR_SOP_CLASS_UID:
            rdsr_files.append(f)
        elif getattr(f, 'Modality', None) == 'PT' and image_type[0] == 'ORIGINAL':
            pet_files.append(f)
    return rdsr_files, pet_files


# SRのコード
CT_ACQUISITION_CODE = '113819'
CT_ACCUMULATED_DOSE_DATA_CODE = '113811'
CT_DOSE_LENGTH_PRODUCT_TOTAL_CODE = '113813'

# CT Acquisitionの下にあるコンテナのコード
CT_ACQUISITION_PARAMETERS = '113822'
CT_XRAY_SOURCE_PARAMETERS = '113831'
CT_DOSE = '113829'
DOSE_CHECK_NOTIFICATION_DETAILS = '113908'
DEVICE_ROLE_IN_PROCEDURE = '113876'

# 新しい装置ではSRTコードの代わりにSNOMED CTコードが使われるため、SRTコードに読み替える
CODE_ALIASES = {'408730004': 'G-C32C'}  # Procedure Context

# CT Acquisitionから取得するデータ一覧
# 列名: (CT Acquisitionからのコードの経路, 値の種類)
# 値の種類 NUM: 数値, TEXT: テキスト, CODE: コードの意味
CT_ACQUISITION_FIELDS = {
    'MeanCTDIvol': ((CT_DOSE, '113830'), 'NUM'),
    'DLP': ((CT_DOSE, '113838'), 'NUM'),
    'Comment': (('121106',), 'TEXT'),
    'XRayModulationType': (('113842',), 'TEXT'),
    'CTDIwPhantomType': ((CT_DOSE, '113835'), 'CODE'),
    'AcquisitionProtocol': (('125203',), 'TEXT'),
    'TargetRegion': (('123014',), 'CODE'),
    'CTAcquisitionType': (('113820',), 'CODE'),
    'ProcedureContext': (('G-C32C',), 'CODE'),
    'ExposureTime': ((CT_ACQUISITION_PARAMETERS, '113824'), 'NUM'),
    'ScanningLength': ((CT_ACQUISITION_PARAMETERS, '113825'), 'NUM'),
    'ExposedRange': ((CT_ACQUISITION_PARAMETERS, '113899'), 'NUM'),
    'NominalSingleCollimationWidth': ((CT_ACQUISITION_PARAMETERS, '113826'), 'NUM'),
    'NominalTotalCollimationWidth': ((CT_ACQUISITION_PARAMETERS, '113827'), 'NUM'),
    'PitchFactor': ((CT_ACQUISITION_PARAMETERS, '113828'), 'NUM'),
    'IdentificationoftheXRaySource': ((CT_ACQUISITION_PARAMETERS, CT_XRAY_SOURCE_PARAMETERS, '113832'), 'TEXT'),
    'KVP': ((CT_ACQUISITION_PARAMETERS, CT_XRAY_SOURCE_PARAMETERS, '113733'), 'NUM'),
    'MaximumXRayTubeCurrent': ((CT_ACQUISITION_PARAMETERS, CT_XRAY_SOURCE_PARAMETERS, '113833'), 'NUM'),
    'MeanXRayTubeCurrent': ((CT_ACQUISITION_PARAMETERS, CT_XRAY_SOURCE_PARAMETERS, '113734'), 'NUM'),
    'ExposureTimeperRotation': ((CT_ACQUISITION_PARAMETERS, CT_XRAY_SOURCE_PARAMETERS, '113834'), 'NUM'),
    'DeviceManufacturer': ((DEVICE_ROLE_IN_PROCEDURE, '113878'), 'TEXT'),
    'DeviceSerialNumber': ((DEVICE_ROLE_IN_PROCEDURE, '113880'), 'TEXT'),
    'DLPNotificationValue': ((CT_DOSE, DOSE_CHECK_NOTIFICATION_DETAILS, '113911'), 'NUM'),
    'CTDIvolNotificationValue': ((CT_DOSE, DOSE_CHECK_NOTIFICATION_DETAILS, '113912'), 'NUM'),
    'ReasonforProceeding': ((CT_DOSE, DOSE_CHECK_NOTIFICATION_DETAILS, '113907'), 'TEXT'),
}

# RDSRのヘッダーから取得するデータ一覧
RDSR_HEADER_FIELDS = ['ManufacturerModelName', 'PatientID', 'StudyDate', 'PatientName',
                      'StudyDescription', 'PatientBirthDate', 'PatientSex', 'PatientAge', 'PatientSize', 'PatientWeight']


def concept_code(item):
    '''Content Sequenceの項目のConcept Nameのコードを返す'''
    try:
        code = item.ConceptNameCodeSequence[0].CodeValue
    except MISSING_ERRORS:
        return None
    return CODE_ALIASES.get(code, code)


def children(item):
    '''項目の下にあるContent Sequenceを返す'''
    return item.get('ContentSequence') or []


def find_items(items, path):
    '''pathのコードを順に辿り、一致する項目を全て文書順に返す'''
    for item in items:
        if concept_code(item) == path[0]:
            if len(path) == 1:
                yield item
            else:
                yield from find_items(children(item), path[1:])


def find_content(items, code):
    '''Content Sequenceの中から、Concept Nameのコードが一致する最初の項目を返す'''
    return next(find_items(items, (code,)), None)


def read_value(item, value_type):
    '''項目から値の種類に応じた値を取り出す'''
    if value_type == 'NUM':
        return item.MeasuredValueSequence[0].NumericValue
    if value_type == 'TEXT':
        return item.TextValue
    return item.ConceptCodeSequence[0].CodeMeaning


def separate_CT_Acquisition(rdsr_file):
    '''RDSRファイルのデータを入力し，CT AcquisitionごとのContent Sequenceのリストを出力する'''
    return [children(item) for item in find_items(children(rdsr_file), (CT_ACQUISITION_CODE,))]


def extract_data_from_CT_Acquisition(CTAcquisition):
    '''1つのCT AcquisitionのContent Sequenceを入力し，そのデータを辞書で返す

    同じ項目が複数ある場合（Dual Source CTのX線管など）は最後の値を使う
    データが入っていない項目は空欄とする（数値の0は空欄にしない）
    '''
    data = {}
    for col, (path, value_type) in CT_ACQUISITION_FIELDS.items():
        value = ' '
        for item in find_items(CTAcquisition, path):
            try:
                found = read_value(item, value_type)
            except MISSING_ERRORS:
                continue
            if found is not None and found != '':
                value = found
        data[col] = value
    return data


def extract_CT_Dose_Length_Product_Total(rdsr_file):
    '''RDSRのCT Accumulated Dose DataからCT Dose Length Product Totalを抽出する'''
    total = find_content(children(rdsr_file), CT_ACCUMULATED_DOSE_DATA_CODE)
    total = total and find_content(children(total), CT_DOSE_LENGTH_PRODUCT_TOTAL_CODE)
    try:
        return read_value(total, 'NUM')
    except MISSING_ERRORS:
        return ' '


def extract_data_from_rdsr_header(rdsr_header_col_names, rdsr_file):
    '''1つのRDSRのヘッダーから情報を抽出し，辞書で出力'''
    header = {}
    for name in rdsr_header_col_names:
        value = getattr(rdsr_file, name, ' ')
        header[name] = '' if value is None else str(value)
    return header


def build_rdsr_dataframe(rdsr_files):
    '''RDSRから1つのCT Acquisitionにつき1行のpd.DataFrameを作成する

    患者情報・CT Dose Length Product Totalは同じRDSRのCT Acquisitionの行にだけ付与するため、
    行がずれて別の患者の情報が付くことはない
    '''
    columns = list(CT_ACQUISITION_FIELDS.keys()) + RDSR_HEADER_FIELDS + ['CTDoseLengthProductTotal']

    rows = []
    for r in rdsr_files:
        header = extract_data_from_rdsr_header(RDSR_HEADER_FIELDS, r)
        CDLPT = extract_CT_Dose_Length_Product_Total(r)
        for acquisition in separate_CT_Acquisition(r):
            row = extract_data_from_CT_Acquisition(acquisition)
            row.update(header)
            row['CTDoseLengthProductTotal'] = CDLPT
            rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def extract_information_from_PET(PET):
    '''PETから必要な情報を取得して，pd.DataFrameとして出力'''
    pet_col_name = ['PatientID', 'StudyDate', 'RadionuclideTotalDose']

    rows = []
    for p in PET:
        try:
            dose = p.RadiopharmaceuticalInformationSequence[0].RadionuclideTotalDose
        except MISSING_ERRORS:
            dose = ' '
        rows.append([str(getattr(p, 'PatientID', ' ')), str(getattr(p, 'StudyDate', ' ')), dose])

    pet_df = pd.DataFrame(rows, columns=pet_col_name)
    return pet_df.drop_duplicates().reset_index(drop=True)


def merge_rdsr_and_pet(rdsr_df, pet_df):
    df = pd.merge(rdsr_df, pet_df, how='outer')
    return df


def process(dicom_directory):
    '''指定したディレクトリのRDSRとPETを処理し，pd.DataFrameを返す

    エラーの場合はメッセージを表示してNoneを返す
    '''
    path_of_files = get_file_path(dicom_directory)
    dicom_files = get_dicom_path(path_of_files)

    if len(dicom_files) == 0:
        messagebox.showerror('エラー', 'DICOMファイルが存在しません')
        return None

    rdsr_files, pet_files = separate_dicom_files(dicom_files)
    del dicom_files

    if len(rdsr_files) == 0 and len(pet_files) == 0:
        messagebox.showerror('エラー', 'RDSRとPETファイルが存在しません')
        return None

    df = None
    if len(rdsr_files) != 0:
        df = build_rdsr_dataframe(rdsr_files)
        print('********************RDSRファイルの処理完了********************')
    else:
        messagebox.showwarning('警告', 'RDSRファイルが存在しないため、PETのデータのみ出力します')

    if len(pet_files) != 0:
        pet_df = extract_information_from_PET(pet_files)
        # RDSRとPETを結合
        df = pet_df if df is None else merge_rdsr_and_pet(df, pet_df)
        print('**********************PETデータの処理完了*********************')

    return df


def write_csv(df, path):
    '''csvをcp932で出力する。cp932で表せない文字がある場合はBOM付きUTF-8で出力する'''
    try:
        df.to_csv(path, index=False, encoding='cp932')
    except UnicodeEncodeError:
        df.to_csv(path, index=False, encoding='utf-8-sig')
        print('cp932で表せない文字が含まれていたため、BOM付きUTF-8で保存しました')


def main():
    '''各関数を実施し，RDSRとPETのデータをcsvとして出力'''
    print('**************************処理開始****************************')
    desktop_dir = os.path.expanduser("~") + '/Desktop'
    dicom_directory = select_directory(desktop_dir)
    if dicom_directory == '':
        sys.exit(0)

    df = process(dicom_directory)
    if df is None:
        sys.exit(0)

    # 最初に選択したdirectoryにcsvとしてデータを出力
    write_csv(df, dicom_directory + '/' + str(datetime.date.today()) + '.csv')

    print('**************************処理完了****************************')
    messagebox.showinfo('処理完了', str(dicom_directory)+'にデータが保存されました')


if __name__ == '__main__':
    main()
