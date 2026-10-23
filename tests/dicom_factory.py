'''テスト用の合成RDSR・PETファイルを作成するヘルパー'''
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

RDSR_SOP_CLASS = '1.2.840.10008.5.1.4.1.1.88.67'
PET_SOP_CLASS = '1.2.840.10008.5.1.4.1.1.128'


def _concept(code, scheme='DCM'):
    c = Dataset()
    c.CodeValue = code
    c.CodingSchemeDesignator = scheme
    c.CodeMeaning = code
    return Sequence([c])


def num(code, value):
    item = Dataset()
    item.ValueType = 'NUM'
    item.ConceptNameCodeSequence = _concept(code)
    mv = Dataset()
    mv.NumericValue = value
    item.MeasuredValueSequence = Sequence([mv])
    return item


def text(code, value):
    item = Dataset()
    item.ValueType = 'TEXT'
    item.ConceptNameCodeSequence = _concept(code)
    item.TextValue = value
    return item


def code(code_, meaning, scheme='DCM'):
    item = Dataset()
    item.ValueType = 'CODE'
    item.ConceptNameCodeSequence = _concept(code_, scheme)
    c = Dataset()
    c.CodeValue = 'X'
    c.CodingSchemeDesignator = 'DCM'
    c.CodeMeaning = meaning
    item.ConceptCodeSequence = Sequence([c])
    return item


def container(code_, children):
    item = Dataset()
    item.ValueType = 'CONTAINER'
    item.ConceptNameCodeSequence = _concept(code_)
    item.ContentSequence = Sequence(children)
    return item


def ct_acquisition(protocol, ctdivol, dlp, kvp=120, extra_dose=()):
    '''CT Acquisition (113819) コンテナを作成'''
    return container('113819', [
        text('125203', protocol),
        code('123014', 'Chest'),
        code('113820', 'Spiral Acquisition'),
        container('113822', [
            num('113824', 5.0),
            num('113825', 300.0),
            num('113828', 0.8),
            container('113831', [
                text('113832', 'A'),
                num('113733', kvp),
                num('113734', 200),
            ]),
        ]),
        container('113829', [
            num('113830', ctdivol),
            code('113835', 'IEC Body Dosimetry Phantom'),
            num('113838', dlp),
            *extra_dose,
        ]),
        container('113876', [
            text('113878', 'ACME'),
            text('113880', 'SN-1'),
        ]),
    ])


def accumulated(events=None, dlp_total=None, reverse=False):
    '''CT Accumulated Dose Data (113811) コンテナを作成'''
    children = []
    if events is not None:
        children.append(num('113812', events))
    if dlp_total is not None:
        children.append(num('113813', dlp_total))
    if reverse:
        children.reverse()
    return container('113811', children)


def rdsr(patient_id, acquisitions, accumulated_item, study_date='20240101',
         patient_name='Test^Patient'):
    ds = Dataset()
    ds.SOPClassUID = RDSR_SOP_CLASS
    ds.SOPInstanceUID = generate_uid()
    ds.Modality = 'SR'
    ds.PatientID = patient_id
    ds.PatientName = patient_name
    ds.StudyDate = study_date
    ds.ManufacturerModelName = 'Model-X'
    ds.ContentSequence = Sequence([accumulated_item, *acquisitions])
    return ds


def pet(patient_id, dose, study_date='20240101', image_type='ORIGINAL'):
    ds = Dataset()
    ds.SOPClassUID = PET_SOP_CLASS
    ds.SOPInstanceUID = generate_uid()
    ds.Modality = 'PT'
    ds.ImageType = [image_type, 'PRIMARY']
    ds.PatientID = patient_id
    ds.StudyDate = study_date
    info = Dataset()
    info.RadionuclideTotalDose = dose
    ds.RadiopharmaceuticalInformationSequence = Sequence([info])
    return ds


def save(ds, path):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = ds.SOPClassUID
    meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    ds.preamble = b'\0' * 128
    ds.save_as(str(path), enforce_file_format=True)
