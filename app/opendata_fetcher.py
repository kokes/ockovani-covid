import sys, os
from datetime import datetime, date

import requests
import pandas as pd

from app import db, app
from app.models import Import, OckovaciMisto, OckovaniSpotreba, OckovaniDistribuce, OckovaniLide, OckovaniLideEnh, \
    OckovaniRezervace, OckovaniRegistrace

from email import utils as eut

class OpenDataFetcher:
    CENTERS_API = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/prehled-ockovacich-mist.json'
    USED_API = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-spotreba.json'
    DISTRIBUTED_API = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-distribuce.json'
    VACCINATED_CSV = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovaci-mista.csv'
    VACCINATED_ENH_CSV = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-profese.csv'
    REGISTRATION_CSV = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-registrace.csv'
    RESERVATION_CSV = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-rezervace.csv'

    _check_dates = None
    _import = None
    _last_modified = None

    def __init__(self, check_dates = True):
        self._check_dates = check_dates

    def fetch_all(self):
        self._import = Import(status='RUNNING')
        db.session.add(self._import)
        db.session.commit()

        try:
            self._fetch_centers()
            self._fetch_used()
            self._fetch_distributed()
            self._fetch_vaccinated()
            # Test if we have an scraped dataset or not
            if os.environ.get('ODL_VACCINATED_ENH') is not None and os.path.exists(
                    os.environ.get('ODL_VACCINATED_ENH')):
                self._fetch_vaccinated_enh_path(os.environ.get('ODL_VACCINATED_ENH'))
            else:
                self._fetch_vaccinated_enh()
            self._fetch_registrations()
            self._fetch_reservations()

            # delete older data delivery from the same day
            db.session.query(Import).filter(Import.date == date.today()).delete()

        except Exception as e:
            app.logger.error(e)
            self._import.status = 'FAILED'
            self._import.end = datetime.now()
            db.session.commit()
            return False

        self._import.status = 'FINISHED'
        self._import.end = datetime.now()
        self._import.last_modified = self._last_modified
        self._import.date = self._last_modified.date()
        db.session.commit()
        return True

    def _fetch_centers(self):
        """
        It will fetch vaccination centers
        @return:
        """
        data = self._load_json_data(self.CENTERS_API)

        for record in data:
            db.session.merge(OckovaciMisto(
                id=record['ockovaci_misto_id'],
                nazev=record['ockovaci_misto_nazev'],
                okres_id=record['okres_nuts_kod'],
                status=record['operacni_status'],
                adresa=record['ockovaci_misto_adresa'],
                latitude=record['latitude'],
                longitude=record['longitude'],
                nrpzs_kod=format(record['nrpzs_kod'], '011d'),
                minimalni_kapacita=record['minimalni_kapacita'],
                bezbarierovy_pristup=record['bezbarierovy_pristup']
            ))

        app.logger.info('Fetching opendata - vaccination centers finished.')

    def _fetch_used(self):
        """
        Fetch vacination data from opendata.
        https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-spotreba.csv
        @return:
        """
        data = self._load_json_data(self.USED_API)

        db.session.query(OckovaniSpotreba).delete()

        for record in data:
            datum = record['datum']
            ockovaci_misto_id = record['ockovaci_misto_id']
            ockovaci_latka = record['ockovaci_latka']
            vyrobce = record['vyrobce']
            pouzite_ampulky = record['pouzite_ampulky']
            znehodnocene_ampulky = record['znehodnocene_ampulky']
            pouzite_davky = record['pouzite_davky']
            znehodnocene_davky = record['znehodnocene_davky']

            spotreba = db.session.query(OckovaniSpotreba) \
                .filter(OckovaniSpotreba.datum == datum,
                        OckovaniSpotreba.ockovaci_misto_id == ockovaci_misto_id,
                        OckovaniSpotreba.ockovaci_latka == ockovaci_latka) \
                .one_or_none()

            if spotreba is None:
                db.session.add(OckovaniSpotreba(
                    datum=datum,
                    ockovaci_misto_id=ockovaci_misto_id,
                    ockovaci_latka=ockovaci_latka,
                    vyrobce=vyrobce,
                    pouzite_ampulky=pouzite_ampulky,
                    znehodnocene_ampulky=znehodnocene_ampulky,
                    pouzite_davky=pouzite_davky,
                    znehodnocene_davky=znehodnocene_davky
                ))
            else:
                spotreba.pouzite_ampulky += pouzite_ampulky
                spotreba.znehodnocene_ampulky += znehodnocene_ampulky
                spotreba.pouzite_davky += pouzite_davky
                spotreba.znehodnocene_davky += znehodnocene_davky
                db.session.merge(spotreba)

        app.logger.info('Fetching opendata - used vaccines finished.')

    def _fetch_distributed(self):
        """
        Fetch distribution files from opendata.
        https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-distribuce.csv
        @return:
        """
        data = self._load_json_data(self.DISTRIBUTED_API)

        db.session.query(OckovaniDistribuce).delete()

        for record in data:
            datum = record['datum']
            ockovaci_misto_id = record['ockovaci_misto_id']
            cilove_ockovaci_misto_id = record['cilove_ockovaci_misto_id']
            ockovaci_latka = record['ockovaci_latka']
            vyrobce = record['vyrobce']
            akce = record['akce']
            pocet_ampulek = record['pocet_ampulek']
            pocet_davek = record['pocet_davek']

            distribuce = db.session.query(OckovaniDistribuce) \
                .filter(OckovaniDistribuce.datum == datum,
                        OckovaniDistribuce.ockovaci_misto_id == ockovaci_misto_id,
                        OckovaniDistribuce.cilove_ockovaci_misto_id == cilove_ockovaci_misto_id,
                        OckovaniDistribuce.ockovaci_latka == ockovaci_latka,
                        OckovaniDistribuce.akce == akce) \
                .one_or_none()

            if distribuce is None:
                db.session.add(OckovaniDistribuce(
                    datum=datum,
                    ockovaci_misto_id=ockovaci_misto_id,
                    cilove_ockovaci_misto_id=cilove_ockovaci_misto_id,
                    ockovaci_latka=ockovaci_latka,
                    vyrobce=vyrobce,
                    akce=akce,
                    pocet_ampulek=pocet_ampulek,
                    pocet_davek=pocet_davek
                ))
            else:
                distribuce.pocet_ampulek += pocet_ampulek
                distribuce.pocet_davek += pocet_davek
                db.session.merge(distribuce)

        app.logger.info('Fetching opendata - distributed vaccines finished.')

    def _fetch_vaccinated(self):
        """
        Fetch distribution files from opendata.
        https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovaci-mista.csv
        @return:
        """
        data = self._load_csv_data(self.VACCINATED_CSV)

        df = data.groupby(["datum", "vakcina", "kraj_nuts_kod", "kraj_nazev", "zarizeni_kod", "zarizeni_nazev",
                          "poradi_davky", "vekova_skupina"]) \
            .size() \
            .reset_index(name='pocet')

        df['poradi_davky'] = df['poradi_davky'].astype('int')

        db.session.query(OckovaniLide).delete()

        for idx, row in df.iterrows():
            db.session.add(OckovaniLide(
                datum=row['datum'],
                vakcina=row['vakcina'],
                kraj_nuts_kod=row['kraj_nuts_kod'],
                kraj_nazev=row['kraj_nazev'],
                zarizeni_kod=row['zarizeni_kod'],
                zarizeni_nazev=row['zarizeni_nazev'],
                poradi_davky=row['poradi_davky'],
                vekova_skupina=row['vekova_skupina'],
                pocet=row['pocet']
            ))

        app.logger.info('Fetching opendata - vaccinated people finished.')

    def _fetch_vaccinated_enh(self):
        """
        Fetch distribution files from opendata.
        https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovaci-profese.csv
        @return:
        """
        data = self._load_csv_data(self.VACCINATED_ENH_CSV).fillna(0)

        df = data.groupby(
            ["datum", "vakcina", "kraj_nuts_kod", "zarizeni_kod", "poradi_davky", "indikace_zdravotnik",
             "indikace_socialni_sluzby", "indikace_ostatni", "indikace_pedagog",
             "indikace_skolstvi_ostatni"]).size().reset_index(name='pocet')

        db.session.query(OckovaniLideEnh).delete()

        for row in df.itertuples(index=False):
            db.session.add(OckovaniLideEnh(
                datum=row[0],
                vakcina=row[1],
                kraj_nuts_kod=row[2],
                zarizeni_kod=format(int(row[3]), '011d'),
                poradi_davky=row[4],
                vekova_skupina='N/A',
                pohlavi='N/A',
                okres_bydliste_kod='N/A',
                indikace_zdravotnik=row[5],
                indikace_socialni_sluzby=row[6],
                indikace_ostatni=row[7],
                indikace_pedagog=row[8],
                indikace_skolstvi_ostatni=row[9],
                pocet=row[10]
            ))

        app.logger.info('Fetching opendata - vaccinated people enhanced finished.')

    def _fetch_vaccinated_enh_path(self, path):
        """
        For the future if there will be any better source - from scraping for example.
        @return:
        """
        data = pd.read_csv(path)
        data['orp_bydl_kod'] = data['orp_bydliste_kod'].astype(str).str[:4]

        df = data.groupby(
            ["datum_vakcinace", "vakcina", "kraj_kod", "zarizeni_kod", "poradi_davky", "vekova_skupina", "pohlavi",
             "orp_bydl_kod", "indikace_zdravotnik",
             "indikace_socialni_sluzby", "indikace_ostatni", "indikace_pedagog",
             "indikace_skolstvi_ostatni"]).size().reset_index(name='pocet')

        db.session.query(OckovaniLideEnh).delete()

        for row in df.itertuples(index=False):
            db.session.add(OckovaniLideEnh(
                datum=row[0],
                vakcina=row[1],
                kraj_nuts_kod=row[2],
                zarizeni_kod=format(int(row[3]), '011d'),
                poradi_davky=row[4],
                vekova_skupina=row[5],
                pohlavi=row[6],
                okres_bydliste_kod=row[7],
                indikace_zdravotnik=row[8],
                indikace_socialni_sluzby=row[9],
                indikace_ostatni=row[10],
                indikace_pedagog=row[11],
                indikace_skolstvi_ostatni=row[12],
                pocet=row[13]
            ))

        app.logger.info('Fetching data - vaccinated people enhanced finished.')

    def _fetch_registrations(self):
        """
        Fetch registrations from opendata.
        https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-registrace.csv
        @return:
        """
        data = self._load_csv_data(self.REGISTRATION_CSV)

        df = data.drop(["ockovaci_misto_nazev", "kraj_nuts_kod", "kraj_nazev"], axis=1)

        df['rezervace'] = df['rezervace'] == '1'
        df['datum_rezervace'] = df['datum_rezervace'].fillna('1970-01-01')

        df = df.groupby(["datum", "ockovaci_misto_id", "vekova_skupina", "povolani", "stat", "rezervace",
                         "datum_rezervace"]) \
            .size() \
            .reset_index(name='pocet')

        mista_result = db.session.query(OckovaciMisto.id).all()
        mista_ids = {id for id, in mista_result}
        missing_ids = []
        missing_count = 0
        missing_sum = 0

        for idx, row in df.iterrows():
            misto_id = row['ockovaci_misto_id']
            pocet = row['pocet']

            if misto_id not in mista_ids:
                missing_count += 1
                missing_sum += pocet
                if misto_id not in missing_ids:
                    missing_ids.append(misto_id)
                    app.logger.warn("Center: '{0}' doesn't exist.".format(misto_id))
                continue

            db.session.add(OckovaniRegistrace(
                datum=row['datum'],
                ockovaci_misto_id=misto_id,
                vekova_skupina=row['vekova_skupina'],
                povolani=row['povolani'],
                stat=row['stat'],
                rezervace=row['rezervace'],
                datum_rezervace=row['datum_rezervace'],
                pocet=pocet,
                import_=self._import
            ))

        if missing_count > 0:
            app.logger.warn("Some centers doesn't exist - {} rows ({} registrations) skipped.".format(missing_count, missing_sum))

        app.logger.info('Fetching opendata - registrations finished.')

    def _fetch_reservations(self):
        """
        Fetch reservations from opendata.
        https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/ockovani-rezervace.csv
        @return:
        """
        data = self._load_csv_data(self.RESERVATION_CSV)

        df = data.drop(["ockovaci_misto_nazev", "kraj_nuts_kod", "kraj_nazev"], axis=1)

        df['volna_kapacita'] = df['volna_kapacita'].astype('int')
        df['maximalni_kapacita'] = df['maximalni_kapacita'].astype('int')

        mista_result = db.session.query(OckovaciMisto.id).all()
        mista_ids = {id for id, in mista_result}
        missing_ids = []
        missing_count = 0

        for idx, row in df.iterrows():
            misto_id = row['ockovaci_misto_id']

            if misto_id not in mista_ids:
                missing_count += 1
                if misto_id not in missing_ids:
                    missing_ids.append(misto_id)
                    app.logger.warn("Center: '{0}' doesn't exist.".format(misto_id))
                continue

            db.session.add(OckovaniRezervace(
                datum=row['datum'],
                ockovaci_misto_id=misto_id,
                volna_kapacita=row['volna_kapacita'],
                maximalni_kapacita=row['maximalni_kapacita'],
                kalendar_ockovani=row['kalendar_ockovani'],
                import_=self._import
            ))

        if missing_count > 0:
            app.logger.warn("Some centers doesn't exist - {} rows skipped.".format(missing_count))

        app.logger.info('Fetching opendata - reservations finished.')

    def _load_json_data(self, url):
        try:
            response = requests.get(url=url)
            json = response.json()
            modified = datetime.fromisoformat(json['modified']).replace(tzinfo=None)
            self._check_modified_date(modified)
            return response.json()['data']
        except Exception as e:
            raise Exception(e, "Fetching JSON file '{0}' failed.".format(url))

    def _load_csv_data(self, url):
        try:
            headers = requests.head(url=url).headers
            modified_tuple = eut.parsedate_tz(headers['last-modified'])
            modified_timestamp = eut.mktime_tz(modified_tuple)
            modified = datetime.fromtimestamp(modified_timestamp)
            self._check_modified_date(modified)
            return pd.read_csv(url, dtype=object)
        except Exception as e:
            raise Exception(e, "Fetching CSV file '{0}' failed.".format(url))

    def _check_modified_date(self, modified):
        if self._check_dates and modified.date() < date.today():
            raise Exception("File was not updated today.")

        if self._last_modified is None or self._last_modified < modified:
            self._last_modified = modified


if __name__ == '__main__':
    arguments = sys.argv[1:]
    if len(arguments) != 1:
        print('Invalid option.')
        exit(1)

    argument = arguments[0]

    fetcher = OpenDataFetcher(False)

    if argument == 'centers':
        fetcher._fetch_centers()
    elif argument == 'used':
        fetcher._fetch_used()
    elif argument == 'distributed':
        fetcher._fetch_distributed()
    elif argument == 'vaccinated':
        fetcher._fetch_vaccinated()
    elif argument == 'vaccinated_enh':
        fetcher._fetch_vaccinated_enh()
    elif argument == 'vaccinated_enh_tmp':
        if os.environ.get('ODL_VACCINATED_ENH') is not None:
            fetcher._fetch_vaccinated_enh_path(os.environ.get('ODL_VACCINATED_ENH'))
    elif argument == 'registrations_reservations':
        fetcher._import = Import(status='RUNNING')
        db.session.add(fetcher._import)
        db.session.commit()
        fetcher._fetch_registrations()
        fetcher._fetch_reservations()
        fetcher._import.status = 'FINISHED'
    else:
        print('Invalid option.')
        exit(1)

    db.session.commit()
