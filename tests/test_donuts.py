import pandas as pd
import pytest

import DoNuTS
import dicom_factory as f


@pytest.fixture(autouse=True)
def reset_messagebox():
    DoNuTS.messagebox.reset_mock()


def write(tmp_path, datasets):
    for i, ds in enumerate(datasets):
        f.save(ds, tmp_path / f'{i}.dcm')


def test_one_row_per_acquisition(tmp_path):
    write(tmp_path, [f.rdsr('A', [f.ct_acquisition('Head', 50, 800), f.ct_acquisition('Neck', 30, 400)],
                            f.accumulated(2, 1200), patient_name='Alpha')])

    df = DoNuTS.process(str(tmp_path))

    assert list(df['AcquisitionProtocol']) == ['Head', 'Neck']
    assert list(df['MeanCTDIvol']) == [50, 30]
    assert list(df['DLP']) == [800, 400]
    assert list(df['KVP']) == [120, 120]
    assert list(df['TargetRegion']) == ['Chest', 'Chest']
    assert list(df['DeviceManufacturer']) == ['ACME', 'ACME']
    assert list(df['PatientName']) == ['Alpha', 'Alpha']
    assert list(df['CTDoseLengthProductTotal']) == [1200, 1200]


def test_rows_do_not_shift_when_event_count_differs(tmp_path):
    # Aはイベント数が3と記載されているがAcquisitionは2つしかない
    write(tmp_path, [
        f.rdsr('A', [f.ct_acquisition('A-1', 10, 100), f.ct_acquisition('A-2', 11, 110)],
               f.accumulated(3, 210), patient_name='Alpha'),
        f.rdsr('B', [f.ct_acquisition('B-1', 20, 400)], f.accumulated(1, 400), patient_name='Bravo'),
    ])

    df = DoNuTS.process(str(tmp_path)).sort_values('AcquisitionProtocol')

    assert len(df) == 3
    assert list(df['PatientName']) == ['Alpha', 'Alpha', 'Bravo']
    assert list(df['PatientID']) == ['A', 'A', 'B']
    assert list(df['CTDoseLengthProductTotal']) == [210, 210, 400]


def test_zero_value_is_not_blank(tmp_path):
    write(tmp_path, [f.rdsr('A', [f.ct_acquisition('Scout', 0, 0)], f.accumulated(1, 0))])

    df = DoNuTS.process(str(tmp_path))

    assert df.loc[0, 'MeanCTDIvol'] == 0
    assert df.loc[0, 'DLP'] == 0
    assert df.loc[0, 'CTDoseLengthProductTotal'] == 0


def test_missing_values_are_blank(tmp_path):
    write(tmp_path, [f.rdsr('A', [f.ct_acquisition('Head', 50, 800)], f.accumulated())])

    df = DoNuTS.process(str(tmp_path))

    assert df.loc[0, 'CTDoseLengthProductTotal'] == ' '
    assert df.loc[0, 'Comment'] == ' '
    assert df.loc[0, 'PatientWeight'] == ' '


def test_dlp_total_found_regardless_of_order(tmp_path):
    write(tmp_path, [f.rdsr('A', [f.ct_acquisition('Head', 50, 800)], f.accumulated(1, 800, reverse=True))])

    df = DoNuTS.process(str(tmp_path))

    assert df.loc[0, 'CTDoseLengthProductTotal'] == 800


def test_dose_check_notification(tmp_path):
    notification = f.container('113908', [f.num('113911', 1000), f.num('113912', 80), f.text('113907', 'Emergency')])
    write(tmp_path, [f.rdsr('A', [f.ct_acquisition('Head', 50, 800, extra_dose=[notification])], f.accumulated(1, 800))])

    df = DoNuTS.process(str(tmp_path))

    assert df.loc[0, 'DLPNotificationValue'] == 1000
    assert df.loc[0, 'CTDIvolNotificationValue'] == 80
    assert df.loc[0, 'ReasonforProceeding'] == 'Emergency'


def test_rdsr_and_pet_are_merged(tmp_path):
    write(tmp_path, [
        f.rdsr('A', [f.ct_acquisition('WB', 5, 500)], f.accumulated(1, 500)),
        f.pet('A', 185000000),
        f.pet('A', 185000000),
        f.pet('A', 185000000, image_type='DERIVED'),
    ])

    df = DoNuTS.process(str(tmp_path))

    assert len(df) == 1
    assert df.loc[0, 'AcquisitionProtocol'] == 'WB'
    assert df.loc[0, 'RadionuclideTotalDose'] == 185000000


def test_pet_only_outputs_pet_data(tmp_path):
    write(tmp_path, [f.pet('A', 185000000)])

    df = DoNuTS.process(str(tmp_path))

    assert list(df.columns) == ['PatientID', 'StudyDate', 'RadionuclideTotalDose']
    assert df.loc[0, 'PatientID'] == 'A'
    DoNuTS.messagebox.showwarning.assert_called_once()


def test_no_rdsr_or_pet_shows_error(tmp_path):
    ds = f.pet('A', 1)
    ds.Modality = 'CT'
    write(tmp_path, [ds])

    assert DoNuTS.process(str(tmp_path)) is None
    DoNuTS.messagebox.showerror.assert_called_once()


def test_no_dicom_shows_error(tmp_path):
    (tmp_path / 'note.txt').write_text('not dicom')
    (tmp_path / 'sub').mkdir()

    assert DoNuTS.process(str(tmp_path)) is None
    DoNuTS.messagebox.showerror.assert_called_once()


def test_pixel_data_is_not_loaded(tmp_path):
    ds = f.pet('A', 1)
    ds.BitsAllocated = 8
    ds.PixelData = b'\0' * 16
    f.save(ds, tmp_path / 'pet.dcm')

    (loaded,) = DoNuTS.get_dicom_path([str(tmp_path / 'pet.dcm')])

    assert 'PixelData' not in loaded


def test_csv_is_cp932_when_possible(tmp_path):
    path = tmp_path / 'out.csv'
    DoNuTS.write_csv(pd.DataFrame({'PatientName': ['山田^太郎']}), str(path))

    assert path.read_bytes().decode('cp932').splitlines() == ['PatientName', '山田^太郎']


def test_csv_falls_back_to_utf8_for_non_cp932_characters(tmp_path):
    path = tmp_path / 'out.csv'
    DoNuTS.write_csv(pd.DataFrame({'PatientName': ['𠮷田^花子']}), str(path))

    assert path.read_text(encoding='utf-8-sig').splitlines() == ['PatientName', '𠮷田^花子']


def test_procedure_context_accepts_srt_and_snomed_codes(tmp_path):
    srt = f.ct_acquisition('SRT', 1, 1)
    srt.ContentSequence.append(f.code('G-C32C', 'Diagnostic', 'SRT'))
    sct = f.ct_acquisition('SCT', 1, 1)
    sct.ContentSequence.append(f.code('408730004', 'Screening', 'SCT'))
    write(tmp_path, [f.rdsr('A', [srt, sct], f.accumulated(2, 2))])

    df = DoNuTS.process(str(tmp_path))

    assert list(df['ProcedureContext']) == ['Diagnostic', 'Screening']


def test_last_xray_source_is_used_for_dual_source(tmp_path):
    acquisition = f.ct_acquisition('Dual', 1, 1)
    parameters = DoNuTS.find_content(acquisition.ContentSequence, '113822')
    parameters.ContentSequence.append(f.container('113831', [f.text('113832', 'B'), f.num('113733', 140)]))
    write(tmp_path, [f.rdsr('A', [acquisition], f.accumulated(1, 1))])

    df = DoNuTS.process(str(tmp_path))

    assert df.loc[0, 'IdentificationoftheXRaySource'] == 'B'
    assert df.loc[0, 'KVP'] == 140


def test_reason_for_proceeding_is_read_from_notification_only(tmp_path):
    alert = f.container('113900', [f.text('113907', 'AlertReason')])
    write(tmp_path, [f.rdsr('A', [f.ct_acquisition('Head', 50, 800, extra_dose=[alert])], f.accumulated(1, 800))])

    df = DoNuTS.process(str(tmp_path))

    assert df.loc[0, 'ReasonforProceeding'] == ' '
