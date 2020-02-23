import pydicom
import os
import sys
import glob
import pandas as pd
import datetime
import gc
import tkinter
from tkinter import filedialog
from tkinter import messagebox
from tqdm import tqdm

class create_csv:
    '''DICOMデータのheaderから情報をcsvとして出力
    最終的なcsvのcolmns name
    col_name = ['PatientName', 'PatientID', 'StudyDate', 'StudyDescription', 'PatientBirthDate', 'PatientSex', 'PatientAge',
                'PatientSize', 'PatientWeight', 'RadionuclideTotalDose','meanCTDIvol', 'DLP', 'AcquisitionProtocol']
    '''

    def __init__(self, desktop_dir):
        self.desktop_dir = desktop_dir
        self.dicom_dir_path = ''
        self.dicom_path = []
        self.dicom_file = []
        self.rdsr_file = []
        self.pet_file = []
        self.events = []
        self.rdsr_df = pd.DataFrame()
        self.pet_df = pd.DataFrame()


    def get_dicom_path(self):
        '''GUIでDICOMファイルが入ったdirectoryを指定する'''
        tk = tkinter.Tk()
        tk.withdraw()
        self.dicom_dir_path = filedialog.askdirectory(initialdir = self.desktop_dir, title="DICOMファイルが含まれるフォルダを選択")
        if self.dicom_dir_path == "":
            messagebox.showerror('エラー', 'フォルダが選択されませんでした')
            sys.exit(0)
        self.dicom_path = glob.glob(self.dicom_dir_path + '\\**\\*', recursive=True)

        return self.dicom_dir_path


    def get_dicom_file(self):
        '''DICOMデータをリストに追加'''
        for path in tqdm(self.dicom_path,desc='データを読み込み中'):
            try:
                self.dicom_file.append(pydicom.dcmread(path))
            except:
                pass
        
        return self.dicom_file


    def separate_rdsr_and_pet_file(self):
        '''dicom_fileをrdsr_fileとpet_fileに分割し，PETのデータ数を返り値とする'''
        for file in tqdm(self.dicom_file,desc='データを分割中'):
            try:
                if file.SOPClassUID=='1.2.840.10008.5.1.4.1.1.88.67':
                    self.rdsr_file.append(file)
                elif file.Modality == 'PT' and file.ImageType[0] == 'ORIGINAL':
                    self.pet_file.append(file)
            except :
                pass

        # メモリの開放
        del self.dicom_file
        gc.collect()

        return int(len(self.rdsr_file)), int(len(self.pet_file))


    def get_events_from_rdsr(self):
        '''CTの曝射回数をRDSRからself.eventsとして読み取る'''
        # EventsのEV
        Events_code = '113812'

        for _, rdsr in enumerate(self.rdsr_file):
            for _, rdsr2 in enumerate(rdsr.ContentSequence):
                try:
                    nest1_len = len(rdsr2.ContentSequence)
                    for i in range(nest1_len):
                        EveorAP = rdsr2.ContentSequence[i].ConceptNameCodeSequence[0].CodeValue
                        if EveorAP == Events_code:
                            self.events.append(int(rdsr2.ContentSequence[i].MeasuredValueSequence[0].NumericValue))
                except:
                    pass


    def create_rdsr_df(self):
        '''self.rdsr_fileから必要なheader情報だけ抜き出してrdsr_dfとして保存'''
        # 各データのEV
        CTDI_code = '113830'
        DLP_code = '113838'
        AcquisitionProtocol_code = '125203'

        # データを入れるdictionaryを作成
        rdsr_col_name = ['meanCTDIvol', 'DLP', 'AcquisitionProtocol', 'PatientID', 'StudyDate', 'PatientName',
                         'StudyDescription', 'PatientBirthDate', 'PatientSex', 'PatientAge', 'PatientSize', 'PatientWeight']
        rdsr_data_dic = {col:[] for col in rdsr_col_name}

 
        for _, rdsr in enumerate(self.rdsr_file):
            for _, rdsr2 in enumerate(rdsr.ContentSequence):
                try:
                    nest1_len = len(rdsr2.ContentSequence)
                    for i in range(nest1_len):
                        AP = rdsr2.ContentSequence[i].ConceptNameCodeSequence[0].CodeValue
                        if AP == AcquisitionProtocol_code:
                            rdsr_data_dic['AcquisitionProtocol'].append(rdsr2.ContentSequence[i].TextValue)
                        try:
                            nest2_len = len(rdsr2.ContentSequence[i].ContentSequence)
                            for j in range(nest2_len):
                                CTDIorDLP = rdsr2.ContentSequence[i].ContentSequence[j].ConceptNameCodeSequence[0].CodeValue
                                if CTDIorDLP == CTDI_code:
                                    rdsr_data_dic['meanCTDIvol'].append(rdsr2.ContentSequence[i].ContentSequence[j].MeasuredValueSequence[0].NumericValue)
                                if CTDIorDLP == DLP_code:
                                    rdsr_data_dic['DLP'].append(rdsr2.ContentSequence[i].ContentSequence[j].MeasuredValueSequence[0].NumericValue)
                        except:
                            pass
                except:
                    pass 

        # CTDIvol, DLP, AcquisitionProtocol以外のデータをdictionaryに入れる
        for num, rdsr in enumerate(self.rdsr_file):
            for eve in range(int(self.events[num])):
                rdsr_data_dic['PatientID'].append(str(getattr(rdsr, 'PatientID')))
                rdsr_data_dic['StudyDate'].append(str(getattr(rdsr, 'StudyDate')))
                rdsr_data_dic['PatientName'].append(str(getattr(rdsr, 'PatientName')))
                rdsr_data_dic['StudyDescription'].append(str(getattr(rdsr, 'StudyDescription')))
                rdsr_data_dic['PatientBirthDate'].append(str(getattr(rdsr, 'PatientBirthDate')))
                rdsr_data_dic['PatientSex'].append(str(getattr(rdsr, 'PatientSex')))
                rdsr_data_dic['PatientAge'].append(str(getattr(rdsr, 'PatientAge')))
                rdsr_data_dic['PatientSize'].append(str(getattr(rdsr, 'PatientSize')))
                rdsr_data_dic['PatientWeight'].append(str(getattr(rdsr, 'PatientWeight')))

        self.rdsr_df = pd.DataFrame.from_dict(rdsr_data_dic, orient='index').T

        # ScoutのCTDIvol・DLPが表示されない場合の処理
        if len(rdsr_data_dic['AcquisitionProtocol']) != len(rdsr_data_dic['DLP']):
            scout_list = ['Topogram', 'Scout view', 'Scanogram', 'Surview', 'Preview', 'Pilot']
            for i in scout_list:
                self.rdsr_df = self.rdsr_df[self.rdsr_df['AcquisitionProtocol'] != i]
            self.rdsr_df.reset_index(inplace=True, drop=True)
            for key in rdsr_col_name[0:2]:
                self.rdsr_df[key] = rdsr_data_dic[key]

        # メモリの開放
        del rdsr_data_dic, rdsr_col_name
        gc.collect()


    def create_pet_df (self):
        '''self.pet_fileから必要なheader情報だけ抜き出してpet_dfとして保存'''
        pet_col_name = ['PatientName', 'PatientID', 'StudyDate','RadionuclideTotalDose']
        self.pet_df = pd.DataFrame(columns=pet_col_name)

        for file in self.pet_file:
            pet_tmp_data = []
            for col in pet_col_name[0:3]:
                pet_tmp_data.append(str(getattr(file, col)))
            pet_tmp_data.append(file.RadiopharmaceuticalInformationSequence[0].RadionuclideTotalDose)
            tmp_se = pd.Series(pet_tmp_data, index=pet_col_name)
            self.pet_df = self.pet_df.append(tmp_se, ignore_index=True)

        self.pet_df = self.pet_df[~self.pet_df.duplicated()]
        self.pet_df.reset_index(inplace=True, drop=True)


    def create_final_csv(self):
        self.rdsr_df = pd.merge(self.rdsr_df, self.pet_df, how='outer')


    def output_csv(self):
        self.rdsr_df.to_csv(self.dicom_dir_path + '/' + str(datetime.date.today()) + '.csv', index=False)


def main():
    '''GUIでDICOMファイルが入ったdirectoryを指定し，各メソッドを実行'''
    desktop_dir = os.getenv("HOMEDRIVE") + os.getenv("HOMEPATH") + "/Desktop"
    c = create_csv(desktop_dir)
    print('**************************処理開始***************************')
    dcm_path = c.get_dicom_path()
    dcm_file = c.get_dicom_file()
    if int(len(dcm_file)) ==0:
        messagebox.showerror('エラー', 'DICOMファイルが存在しません')
        sys.exit(0)
    num_of_rdsr, num_of_pet = c.separate_rdsr_and_pet_file()
    if num_of_rdsr == 0:
        messagebox.showerror('エラー', 'RDSRファイルが存在しません')
    else:
        c.get_events_from_rdsr()
        c.create_rdsr_df()
        print('********************RDSRファイルの処理完了********************')
    if num_of_pet != 0:
        c.create_pet_df()
        c.create_final_csv()
        print('**********************PETデータの処理完了*********************')
    if num_of_rdsr == 0 and num_of_pet == 0:
        sys.exit()
    c.output_csv()
    print('**************************処理完了***************************')
    messagebox.showinfo('処理完了', str(dcm_path)+'にデータが保存されました')


if __name__ == '__main__':
    main()