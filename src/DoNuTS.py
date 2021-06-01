import os
import sys
import glob
import gc
import datetime
from tqdm import tqdm
import tkinter
from tkinter import filedialog
from tkinter import messagebox

import pydicom
import pandas as pd


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
    return path_of_files


def get_dicom_path(path):
    '''パスを入力し、その中のDICOMだけを出力'''
    dicom_files = []
    for p in tqdm(path, desc='データを読み込み中'):
        try:
            dicom_files.append(pydicom.dcmread(p))
        except:
            pass
    return dicom_files


def separate_dicom_files(dicom_files):
    '''DICOMファイルを入力し、RDSRとPETに分割してそれぞれをタプルで出力'''
    rdsr_files = []
    pet_files = []

    for f in tqdm(dicom_files, desc='データを分割中'):
        try:
            if f.SOPClassUID == '1.2.840.10008.5.1.4.1.1.88.67':
                rdsr_files.append(f)
            elif f.Modality == 'PT' and f.ImageType[0] == 'ORIGINAL':
                pet_files.append(f)
        except:
            pass
    return rdsr_files, pet_files


def separate_CT_Acquisition(rdsr_files):
    '''RDSRファイルのデータを入力し，CTの線量情報が記載されたレベルのネストの情報を出力する'''
    CTAcquisition = []
    for r in rdsr_files[0x0040,0xa730].value:
        try:
            if r[0x0040,0xa043][0][0x0008,0x0100].value == '113819':  # CTAcquisition_code
                CTAcquisition.append(r[0x0040,0xa730])
        except:
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
    tmp_dictionary = {col: [] for col in rdsr_col.keys()}

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
                            except:
                                pass
                except:
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
                            except:
                                pass
                except:
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
                except:
                    pass
        except:
            pass

    # データが入っていない箇所を空欄とする
    for col in rdsr_col.keys():
        if not tmp_dictionary[col]:
            tmp_dictionary[col] = ' '

    return tmp_dictionary


def get_events_from_rdsr(rdsr_files):
    '''CTの曝射回数をRDSRからeventsとして読み取る'''
    # EventsのEV
    TotalNumberofIrradiationEvents_code = '113812'

    for _, r in enumerate(rdsr_files[0x0040,0xa730].value):
        try:
            if r[0x0040,0xa730][0][0x0040,0xa043][0][0x0008,0x0100].value == TotalNumberofIrradiationEvents_code:
                events = r[0x0040,0xa730][0][0x0040,0xa300][0][0x0040,0xa30a].value
        except:
            pass
    return events


def extract_CT_Dose_Length_Product_Total(rdsr_files):
    '''RDSRからCT Dose Length Product Totalを抽出し，辞書で出力'''
    # CT Dose Length Product TotalのEV
    CTDoseLengthProductTotal_code = '113813'

    for _, r in enumerate(rdsr_files[0x0040,0xa730].value):
        try:
            if r[0x0040,0xa730][1][0x0040,0xa043][0][0x0008,0x0100].value == CTDoseLengthProductTotal_code:
                CDLPT = r[0x0040,0xa730][1][0x0040,0xa300][0][0x0040,0xa30a].value
        except:
            pass
    return CDLPT


def extract_data_from_rdsr_header(rdsr_header_col_names, rdsr_files, events):
    '''RDSRのヘッダーから情報を抽出し，辞書で出力'''
    # 空の辞書tmpを作成
    tmp_header_dictionary = {col: [] for col in rdsr_header_col_names}

    for num, rdsr in enumerate(rdsr_files):
        for eve in range(int(events[num])):
            for name in rdsr_header_col_names:
                try:
                    tmp_header_dictionary[name].append(
                        str(getattr(rdsr, name)))
                except:
                    tmp_header_dictionary[name].append(" ")
    return tmp_header_dictionary


def extract_information_from_PET(PET):
    '''PETから必要な情報を取得して，pd.DataFrameとして出力'''
    pet_col_name = ['PatientID', 'StudyDate', 'RadionuclideTotalDose']
    pet_df = pd.DataFrame(columns=pet_col_name)

    for p in PET:
        pet_tmp_data = []
        for col in pet_col_name[0:2]:
            pet_tmp_data.append(str(getattr(p, col)))
        pet_tmp_data.append(
            p.RadiopharmaceuticalInformationSequence[0].RadionuclideTotalDose)
        tmp_se = pd.Series(pet_tmp_data, index=pet_col_name)
        pet_df = pet_df.append(tmp_se, ignore_index=True)

    pet_df = pet_df[~pet_df.duplicated()]
    pet_df.reset_index(inplace=True, drop=True)
    return pet_df


def merge_rdsr_and_pet(rdsr_df, pet_df):
    df = pd.merge(rdsr_df, pet_df, how='outer')
    return df


def main():
    '''各関数を実施し，RDSRとPETのデータをcsvとして出力'''
    print('**************************処理開始****************************')
    # desktop_dir = os.getenv('HOMEDRIVE') + os.getenv('HOMEPATH') + '/Desktop'
    desktop_dir = os.path.expanduser("~") + '/Desktop'
    dicom_directory = select_directory(desktop_dir)
    path_of_files = get_file_path(dicom_directory)
    dicom_files = get_dicom_path(path_of_files)

    # メモリの開放
    del path_of_files
    gc.collect()

    if int(len(dicom_files)) == 0:
        messagebox.showerror('エラー', 'DICOMファイルが存在しません')
        sys.exit(0)
    else:
        rdsr_files, pet_files = separate_dicom_files(dicom_files)

    if int(len(rdsr_files)) == 0:
        messagebox.showerror('エラー', 'RDSRファイルが存在しません')

    elif int(len(rdsr_files)) == 0 and int(len(pet_files)) == 0:
        messagebox.showerror('エラー', 'RDSRとPETファイルが存在しません')
        sys.exit()

    else:
        # RDSRの処理
        CT_Acquisition_set = []
        for r in rdsr_files:
            CT_Acquisition_set.append(separate_CT_Acquisition(r))

        # CT_Acquisition_setから線量情報を抽出し辞書にまとめる
        # 取得するデータ一覧
        rdsr_col = {
            'MeanCTDIvol': '113830', 'DLP': '113838', 'Comment': '121106', 'XRayModulationType': '113842', 'CTDIwPhantomType': '113835',
            'AcquisitionProtocol': '125203', 'TargetRegion': '123014', 'CTAcquisitionType': '113820', 'ProcedureContext': 'G-C32C',
            'ExposureTime': '113824', 'ScanningLength': '113825', 'ExposedRange': '113899', 'NominalSingleCollimationWidth': '113826', 'NominalTotalCollimationWidth': '113827', 'PitchFactor': '113828',
            'IdentificationoftheXRaySource': '113832', 'KVP': '113733', 'MaximumXRayTubeCurrent': '113833', 'MeanXRayTubeCurrent': '113734', 'ExposureTimeperRotation': '113834',
            'DeviceManufacturer': '113878', 'DeviceSerialNumber': '113880',
            'DLPNotificationValue': '113911', 'CTDIvolNotificationValue': '113912', 'ReasonforProceeding': '113907'
        }
        # 取得するデータを入れるdictionaryを作成
        rdsr_dictionary = {col: [] for col in rdsr_col.keys()}
        for c1 in CT_Acquisition_set:
            for c2 in c1:
                tmp_dictionary = extract_data_from_CT_Acquisition(rdsr_col, c2)
                for n in rdsr_col.keys():
                    rdsr_dictionary[n].append(tmp_dictionary[n])

        # 各データのevent数をリストで保存
        events_list = []
        for r in rdsr_files:
            events_list.append(get_events_from_rdsr(r))

        # 各データのCT Dose Length Product Totalを辞書で保存
        CDLPT_dictionary = {'CTDoseLengthProductTotal': []}
        for num, r in enumerate(rdsr_files):
            for e in range(int(events_list[num])):
                CDLPT_dictionary['CTDoseLengthProductTotal'].append(
                    extract_CT_Dose_Length_Product_Total(r))

        # rdsrのヘッダーから情報を抽出し辞書にまとめる
        # 取得するデータ一覧
        rdsr_header_col_names = ['ManufacturerModelName', 'PatientID', 'StudyDate', 'PatientName',
                                 'StudyDescription', 'PatientBirthDate', 'PatientSex', 'PatientAge', 'PatientSize', 'PatientWeight']
        # 取得するデータを入れるdictionaryを作成
        rdsr_header_dictionary = {col: [] for col in rdsr_header_col_names}
        tmp_dictionary = extract_data_from_rdsr_header(
            rdsr_header_col_names, rdsr_files, events_list)
        for n in rdsr_header_col_names:
            for num in range(len(tmp_dictionary['PatientID'])):
                rdsr_header_dictionary[n].append(tmp_dictionary[n][num])

        rdsr_dictionary.update(rdsr_header_dictionary)
        rdsr_dictionary.update(CDLPT_dictionary)
        rdsr_df = pd.DataFrame.from_dict(rdsr_dictionary, orient='index').T
        print('********************RDSRファイルの処理完了********************')
        del dicom_files, rdsr_files
        gc.collect()

    if len(pet_files) != 0:
        # PETの処理
        pet_df = extract_information_from_PET(pet_files)
        # RDSRとPETを結合
        rdsr_df = merge_rdsr_and_pet(rdsr_df, pet_df)
        print('**********************PETデータの処理完了*********************')
        # メモリの開放
        del pet_files, pet_df
        gc.collect()

    # 最初に選択したdirectoryにcsvとしてデータを出力
    rdsr_df.to_csv(dicom_directory + '/' + str(datetime.date.today()) + '.csv', index=False, encoding='cp932')

    print('**************************処理完了****************************')
    messagebox.showinfo('処理完了', str(dicom_directory)+'にデータが保存されました')


if __name__ == '__main__':
    main()