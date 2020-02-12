# DoNuTS🍩
**Do**se Counter for **Nu**clear Medicine and C**T** **S**ystems

## DoNuTSとは？
DoNuTSとはRDSR(Radiation Dose Structual Report)とDICOM(Digital Imaging and Cmmunications in Medicine)ヘッダーから線量情報と患者情報を抽出するオープンソースソフトウェアです。

## 抽出する線量情報と患者情報
- meanCTDIvol  
- DLP  
- Acquisition Protocol  
- Patient ID  
- StudyDate  
- Patient Name  
- Study Description  
- Patient BirthDate  
- Patient Sex  
- Patient Age  
- Patient Size  
- Patient Weight  
- Radionuclide Total Dose　(only PET/CT)  

## DoNuTSの使い方
1. 右上にある緑色の**Clone or download**をクリック
1. DoNuTS.exeを含むファイルがPC内にダウンロード
1. DoNuTS.exeをダブルクリック
1. ポップアップが表示され、あらかじめPC内に保存してあるRDSRやDICOMファイルが入ったフォルダを選択
1. 処理が開始
1. 処理終了後、4で選択したフォルダ内に**yyyy-mm-dd.csv**の形式で**処理を行った日付.csv**として抽出したデータが保存されます

## 検証装置
SIEMENS製のRDSRとPET画像については検証済み

## ソースコードの実行環境
| ソフトやパッケージ名 | 開発時点 | 現状 |
|:-----------|:------------|:------------|
| OS | Windows 10 ori (64bit) | Windows 10 ori (64bit) |
| Python | 3.6.9 | 3.6.9 |
| pandas | 0.25.3 | 0.25.3 |
| pydicom | 1.4.1 | 1.4.1 |
| pyinstaller | 4.0.dev0+55c8855d9d | 4.0.dev0+55c8855d9d |
| tqdm | 4.42.0 | 4.42.0 |

## exe化
本ソフトウェアのexe化には`pyinstaller`を使用した．開発版を使用することでWindows7の端末でも動作することを確認した．もし，ソースコードを編集してexe化を行う場合，`DoNuTS.py`が存在するディレクトリに移動して
```python
pyinstaller DoNuTS.py --onefile --clean --icon=DoNuTS.ico
```
でexe化を行うことができます．

## その他
バグの報告や追加機能のご希望のは[issues](https://github.com/radmodel/DoNuTS/issues)までお願いします