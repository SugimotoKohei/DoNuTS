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


def find_content(items, code):
    '''Content Sequenceの中から、Concept Nameのコードが一致する最初の項目を返す'''
    for item in items:
        try:
            if item[0x0040,0xa043][0][0x0008,0x0100].value == code:
                return item
        except MISSING_ERRORS:
            pass
    return None


def separate_CT_Acquisition(rdsr_file):
    '''RDSRファイルのデータを入力し，CTの線量情報が記載されたレベルのネストの情報を出力する'''
    CTAcquisition = []
    try:
        content = rdsr_file[0x0040,0xa730].value
    except MISSING_ERRORS:
        return CTAcquisition
    for r in content:
        try:
            if r[0x0040,0xa043][0][0x0008,0x0100].value == '113819':  # CTAcquisition_code
                CTAcquisition.append(r[0x0040,0xa730])
        except MISSING_ERRORS:
            pass
    return CTAcquisition


def extract_data_from_CT_Acquisition(rdsr_col, CTAcquisition):
    '''1つのCT Acquisitionを入力し，そのデータを辞書で返す'''
    # 各データの区切り部分のEV
    CTAcquisitionParameters_code = '113822'
    CTXraySourceParameters_code = '113831'
    CTDose_code = '113829'
    DeviceRoleinProcedure_code = '113876'
    DoseCheckNotificationDetails_code = '113908'

    # 空の辞書tmpを作成
    tmp_dictionary = {col: None for col in rdsr_col.keys()}

    for _, nest1 in enumerate(CTAcquisition.value):
        try:
            if nest1[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['AcquisitionProtocol']:
                tmp_dictionary['AcquisitionProtocol'] = nest1[0x0040, 0xa160].value
            elif nest1[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['TargetRegion']:
                tmp_dictionary['TargetRegion'] = nest1[0x0040,0xa168][0][0x0008, 0x0104].value
            elif nest1[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['CTAcquisitionType']:
                tmp_dictionary['CTAcquisitionType'] = nest1[0x0040,0xa168][0][0x0008, 0x0104].value
            elif nest1[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['ProcedureContext']:
                tmp_dictionary['ProcedureContext'] = nest1[0x0040,0xa168][0][0x0008, 0x0104].value
            elif nest1[0x0040,0xa043][0][0x0008,0x0100].value == CTAcquisitionParameters_code:
                try:
                    for _, nest2 in enumerate(nest1[0x0040,0xa730].value):
                        if nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['ExposureTime']:
                            tmp_dictionary['ExposureTime'] = nest2[0x0040,0xa300][0][0x0040,0xa30a].value
                        elif nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['ScanningLength']:
                            tmp_dictionary['ScanningLength'] = nest2[0x0040,0xa300][0][0x0040,0xa30a].value
                        elif nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['ExposedRange']:
                            tmp_dictionary['ExposedRange'] = nest2[0x0040,0xa300][0][0x0040,0xa30a].value
                        elif nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['NominalSingleCollimationWidth']:
                            tmp_dictionary['NominalSingleCollimationWidth'] = nest2[0x0040,0xa300][0][0x0040,0xa30a].value
                        elif nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['NominalTotalCollimationWidth']:
                            tmp_dictionary['NominalTotalCollimationWidth'] = nest2[0x0040,0xa300][0][0x0040,0xa30a].value
                        elif nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['PitchFactor']:
                            tmp_dictionary['PitchFactor'] = nest2[0x0040,0xa300][0][0x0040,0xa30a].value
                        elif nest2[0x0040,0xa043][0][0x0008,0x0100].value == CTXraySourceParameters_code:
                            try:
                                for _, nest3 in enumerate(nest2[0x0040,0xa730].value):
                                    if nest3[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['IdentificationoftheXRaySource']:
                                        tmp_dictionary['IdentificationoftheXRaySource'] = nest3[0x0040,0xa160].value
                                    elif nest3[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['KVP']:
                                        tmp_dictionary['KVP'] = nest3[0x0040,0xa300][0][0x0040,0xa30a].value
                                    elif nest3[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['MaximumXRayTubeCurrent']:
                                        tmp_dictionary['MaximumXRayTubeCurrent'] = nest3[0x0040,0xa300][0][0x0040,0xa30a].value
                                    elif nest3[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['MeanXRayTubeCurrent']:
                                        tmp_dictionary['MeanXRayTubeCurrent'] = nest3[0x0040,0xa300][0][0x0040,0xa30a].value
                                    elif nest3[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['ExposureTimeperRotation']:
                                        tmp_dictionary['ExposureTimeperRotation'] = nest3[0x0040,0xa300][0][0x0040,0xa30a].value
                            except MISSING_ERRORS:
                                pass
                except MISSING_ERRORS:
                    pass
            elif nest1[0x0040,0xa043][0][0x0008,0x0100].value == CTDose_code:
                try:
                    for _, nest2 in enumerate(nest1[0x0040,0xa730].value):
                        if nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['MeanCTDIvol']:
                            tmp_dictionary['MeanCTDIvol'] = nest2[0x0040,0xa300][0][0x0040,0xa30a].value
                        elif nest2[0x0040, 0xa043][0][0x0008, 0x0100].value == rdsr_col['CTDIwPhantomType']:
                            tmp_dictionary['CTDIwPhantomType'] = nest2[0x0040,0xa168][0][0x0008,0x0104].value
                        elif nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['DLP']:
                            tmp_dictionary['DLP'] = nest2[0x0040,0xa300][0][0x0040,0xa30a].value
                        elif nest2[0x0040,0xa043][0][0x0008,0x0100].value == DoseCheckNotificationDetails_code:
                            try:
                                for _, nest3 in enumerate(nest2[0x0040,0xa730].value):
                                    if nest3[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['DLPNotificationValue']:
                                        tmp_dictionary['DLPNotificationValue'] = nest3[0x0040,0xa300][0][0x0040,0xa30a].value
                                    elif nest3[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['CTDIvolNotificationValue']:
                                        tmp_dictionary['CTDIvolNotificationValue'] = nest3[0x0040,0xa300][0][0x0040,0xa30a].value
                                    elif nest3[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['ReasonforProceeding']:
                                        tmp_dictionary['ReasonforProceeding'] = nest3[0x0040,0xa160].value
                            except MISSING_ERRORS:
                                pass
                except MISSING_ERRORS:
                    pass
            elif nest1[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['Comment']:
                tmp_dictionary['Comment'] = nest1[0x0040,0xa160].value
            elif nest1[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['XRayModulationType']:
                tmp_dictionary['XRayModulationType'] = nest1[0x0040,0xa160].value
            elif nest1[0x0040,0xa043][0][0x0008,0x0100].value == DeviceRoleinProcedure_code:
                try:
                    for _, nest2 in enumerate(nest1[0x0040,0xa730].value):
                        if nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['DeviceManufacturer']:
                            tmp_dictionary['DeviceManufacturer'] = nest2[0x0040,0xa160].value
                        elif nest2[0x0040,0xa043][0][0x0008,0x0100].value == rdsr_col['DeviceSerialNumber']:
                            tmp_dictionary['DeviceSerialNumber'] = nest2[0x0040,0xa160].value
                except MISSING_ERRORS:
                    pass
        except MISSING_ERRORS:
            pass

    # データが入っていない箇所を空欄とする（数値の0は空欄にしない）
    for col in rdsr_col.keys():
        if tmp_dictionary[col] is None or tmp_dictionary[col] == '':
            tmp_dictionary[col] = ' '

    return tmp_dictionary


def extract_CT_Dose_Length_Product_Total(rdsr_file):
    '''RDSRのCT Accumulated Dose DataからCT Dose Length Product Totalを抽出する'''
    # CT Accumulated Dose DataとCT Dose Length Product TotalのEV
    CTAccumulatedDoseData_code = '113811'
    CTDoseLengthProductTotal_code = '113813'

    try:
        accumulated = find_content(rdsr_file[0x0040,0xa730].value, CTAccumulatedDoseData_code)
        total = find_content(accumulated[0x0040,0xa730].value, CTDoseLengthProductTotal_code)
        return total[0x0040,0xa300][0][0x0040,0xa30a].value
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
    # 取得するデータ一覧
    rdsr_col = {
        'MeanCTDIvol': '113830', 'DLP': '113838', 'Comment': '121106', 'XRayModulationType': '113842', 'CTDIwPhantomType': '113835',
        'AcquisitionProtocol': '125203', 'TargetRegion': '123014', 'CTAcquisitionType': '113820', 'ProcedureContext': 'G-C32C',
        'ExposureTime': '113824', 'ScanningLength': '113825', 'ExposedRange': '113899', 'NominalSingleCollimationWidth': '113826', 'NominalTotalCollimationWidth': '113827', 'PitchFactor': '113828',
        'IdentificationoftheXRaySource': '113832', 'KVP': '113733', 'MaximumXRayTubeCurrent': '113833', 'MeanXRayTubeCurrent': '113734', 'ExposureTimeperRotation': '113834',
        'DeviceManufacturer': '113878', 'DeviceSerialNumber': '113880',
        'DLPNotificationValue': '113911', 'CTDIvolNotificationValue': '113912', 'ReasonforProceeding': '113907'
    }
    rdsr_header_col_names = ['ManufacturerModelName', 'PatientID', 'StudyDate', 'PatientName',
                             'StudyDescription', 'PatientBirthDate', 'PatientSex', 'PatientAge', 'PatientSize', 'PatientWeight']
    columns = list(rdsr_col.keys()) + rdsr_header_col_names + ['CTDoseLengthProductTotal']

    rows = []
    for r in rdsr_files:
        header = extract_data_from_rdsr_header(rdsr_header_col_names, r)
        CDLPT = extract_CT_Dose_Length_Product_Total(r)
        for acquisition in separate_CT_Acquisition(r):
            row = extract_data_from_CT_Acquisition(rdsr_col, acquisition)
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
    df.to_csv(dicom_directory + '/' + str(datetime.date.today()) + '.csv', index=False, encoding='cp932')

    print('**************************処理完了****************************')
    messagebox.showinfo('処理完了', str(dicom_directory)+'にデータが保存されました')


if __name__ == '__main__':
    main()
