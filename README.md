# DoNuTS🍩
**Do**se Counter for **Nu**clear Medicine and C**T** **S**ystems
![DoNuTS](https://user-images.githubusercontent.com/33772302/74533233-71119600-4f74-11ea-9348-e21f60da4957.png)

## DoNuTSとは？
DoNuTSとはRDSR(Radiation Dose Structual Report)とDICOM(Digital Imaging and Cmmunications in Medicine)ヘッダーから線量情報と患者情報を抽出するオープンソースソフトウェアです．Windows上で動作します．


## DoNuTSの使い方
1. 右上にある緑色の**Clone or download**をクリック
1. **DoNuTS.exe**を含むファイルがPC内にダウンロード
1. **DoNuTS.exe**をダブルクリック
1. ポップアップが表示され、あらかじめPC内に保存してあるRDSRやDICOMファイルが入ったフォルダを選択
1. 処理が開始
1. 処理終了後、4で選択したフォルダ内に**処理を行った日付.csv**としてcsvで抽出したデータが保存されます  

## 抽出する線量情報と患者情報
- Mean CTDIvol
- DLP
- X-Ray Modulation Type
- CTDIw Phantom Type
- Acquisition Protocol
- Target Region
- CT Acquisition Type
- Procedure Context
- Exposure Time
- Scanning Length
- Exposed Range
- Nominal Single Collimation Width
- Nominal Total Collimation Width
- Pitch Factor
- Identification of the X-Ray Source
- KVP
- Maximum X-Ray Tube Current
- Mean X-Ray Tube Current
- Exposure Time per Rotation
- Device Manufacturer
- Device Serial Number
- Manufacturer Model Name
- Patient ID
- Study Date
- Patient Name
- Study Description
- Patient BirthDate
- Patient Sex
- Patient Age
- Patient Size
- Patient Weight
- CT Dose Length Product Total
- Radionuclide Total Dose　(only PET/CT)  

## 想定される使い方
- 被ばく線量管理  
線量管理ソフトを導入していない施設では，被ばく線量管理は多くの時間と手間のかかる作業となります．そのような施設はDoNuTSを使えばその苦労から解放されます．まず，あらかじめCT検査後の各患者のRDSRファイルをある場所に保存しておく，もしくはPACS上に保存し，実際に被ばく線量管理を行う際にRDSRをExportするなどしてRDSRを一か所に集めます．その後，**DoNuTS.exe**を使用します．そうすれば正確かつ簡便にRDSRから線量情報を抽出することができ，線量管理を円滑に行うことができます．  

こちらの記事も参考にしてください．  
[被ばく線量情報抽出ソフト『DoNuTS』を作りました - 放射線技術×データサイエンス](https://radmodel.hatenablog.com/entry/2020/04/07/175556)

## 検証装置
- CanonのCT装置のRDSR
- SiemensのCT装置のRDSRとPET/CT装置のRDSRとPET画像

## ソースコードの実行環境
| ソフトやパッケージ名 | 開発時点 | 現状 |
|:-----------|:------------|:------------|
| OS | Windows 10 pro (64bit) | Windows 10 pro (64bit) |
| Python | 3.6.9 | 3.6.9 |
| pandas | 0.25.3 | 0.25.3 |
| pydicom | 1.4.1 | 1.4.1 |
| pyinstaller | 4.0.dev0+55c8855d9d | 4.0.dev0+55c8855d9d |
| tqdm | 4.42.0 | 4.42.0 |

## exe化
本ソフトウェアのexe化には`pyinstaller`を使用しました．開発版を使用することでWindows7の端末でも動作することを確認しました．もし，ソースコードを編集してexe化を行う場合，`DoNuTS.py`が存在するディレクトリに移動して
```
pyinstaller DoNuTS.py --onefile --clean --icon=DoNuTS.ico
```
でexe化を行うことができます．

## その他
バグの報告や追加機能のご希望のは[issues](https://github.com/radmodel/DoNuTS/issues)までお願いします．

### 修正履歴
2020.5.1 線量関連情報に空欄があった際に，空欄として出力するように変更  
2020.5.19 CTとPETの線量情報を結合する際のターゲットに，名前を使用しないように変更
2020.6.8 大幅なコードの変更により取得データ数の大幅な増加