import pandas as pd
import requests
import os

from app import db, app
from app.fetcher.fetcher import Fetcher
from app.models import OckovaciMisto, OckovaniRegistrace


class RegistrationsFetcher(Fetcher):
    """
    Class for updating registrations table.
    """

    REGISTRATIONS_CSV = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-registrace.csv'

    def __init__(self):
        url = os.environ.get('ODL_REGISTRACE_ENH')
        super().__init__(OckovaniRegistrace.__tablename__,
                         url if url is not None and requests.head(
                             url).status_code == 200 else self.REGISTRATIONS_CSV)

    def fetch(self, import_id: int) -> None:
        df = pd.read_csv(self._url)
        app.logger.info("Download of the registration dataset finished.")

        if 'OckovaciCentrumKod' in df:
            # Tailor the dataset to the open one
            df['Datum'] = df['Datum'].astype(str).str[:10]
            df = df.rename(columns={'Datum': 'datum', 'OckovaciCentrumKod': 'ockovaci_misto_id'
                , 'VekovaSkupina': 'vekova_skupina', 'PovolaniNazev': 'povolani'
                , 'Zeme': 'stat', 'Rezervace': 'rezervace'
                , 'DatumRezervace': 'datum_rezervace'})
            # We import only notblocked or blocked with vaccination
            df = df.loc[df['Zruseno'] == 'Ne' & df['ZrusenoReservatic'] == 'Ne' & (
                    (df['Zablokovano'] == 'Ne') | (df['DuvodBlokace'] == 'Ztotožněn, ale již vakcinován'))]
            df['ockovani'] = df['DuvodBlokace'].apply(lambda val: 1 if val == 'Ztotožněn, ale již vakcinován' else 0)
            # Cut the dataframe to the right output
            df = df[
                ['datum', 'ockovaci_misto_id', 'vekova_skupina', 'povolani', 'stat', 'rezervace', 'datum_rezervace',
                 'ockovani']]
            # Ano / Ne
            df['rezervace'] = df['rezervace'].map({'Ano': True, 'Ne': False}).astype('bool')

        else:
            df = df.drop(['ockovaci_misto_nazev', 'kraj_nuts_kod', 'kraj_nazev'], axis=1)
            # set as empty
            df['ockovani'] = -1

        df['rezervace'] = df['rezervace'].fillna(False).astype('bool')
        df['vekova_skupina'] = df['vekova_skupina'].fillna('neuvedeno')
        df['stat'] = df['stat'].fillna('neuvedeno')
        df['datum_rezervace'] = df['datum_rezervace'].fillna('1970-01-01')

        df = df.groupby(df.columns.tolist(), dropna=False).size().reset_index(name='pocet')

        df['import_id'] = import_id

        # filter out missing centers
        size = len(df)
        mista_ids = [r[0] for r in db.session.query(OckovaciMisto.id).all()]
        df = df[df['ockovaci_misto_id'].isin(mista_ids)]

        if size > len(df):
            app.logger.warn("Some centers doesn't exist - {} rows skipped.".format(size - len(df)))

        df.to_sql(self._table, db.engine, if_exists='append', index=False, method=Fetcher._psql_insert_copy)
