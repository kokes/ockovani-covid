from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, or_

from app import db
from app.context import get_import_date, get_import_id
from app.models import OckovaciMisto, Okres, Kraj, OckovaciMistoMetriky


def unique_nrpzs_subquery():
    return db.session.query(OckovaciMisto.nrpzs_kod) \
        .filter(OckovaciMisto.status == True) \
        .group_by(OckovaciMisto.nrpzs_kod) \
        .having(func.count(OckovaciMisto.nrpzs_kod) == 1) \
        .subquery()


def find_centers(filter_column, filter_value):
    centers = db.session.query(OckovaciMisto.id, OckovaciMisto.nazev, Okres.nazev.label("okres"),
                               Kraj.nazev.label("kraj"), OckovaciMisto.longitude, OckovaciMisto.latitude,
                               OckovaciMisto.adresa, OckovaciMisto.status, OckovaciMistoMetriky.registrace_fronta,
                               OckovaciMistoMetriky.registrace_prumer_cekani, OckovaciMistoMetriky.ockovani_odhad_cekani,
                               OckovaciMistoMetriky.registrace_fronta_prumer_cekani) \
        .join(OckovaciMistoMetriky) \
        .outerjoin(Okres, (OckovaciMisto.okres_id == Okres.id)) \
        .outerjoin(Kraj, (Okres.kraj_id == Kraj.id)) \
        .filter(filter_column == filter_value) \
        .filter(OckovaciMistoMetriky.datum == get_import_date()) \
        .filter(or_(OckovaciMisto.status == True, OckovaciMistoMetriky.registrace_fronta > 0,
                    OckovaciMistoMetriky.rezervace_cekajici > 0)) \
        .group_by(OckovaciMisto.id, OckovaciMisto.nazev, Okres.id, Kraj.id, OckovaciMisto.longitude,
                  OckovaciMisto.latitude, OckovaciMisto.adresa, OckovaciMisto.status,
                  OckovaciMistoMetriky.registrace_fronta, OckovaciMistoMetriky.registrace_prumer_cekani,
                  OckovaciMistoMetriky.ockovani_odhad_cekani, OckovaciMistoMetriky.registrace_fronta_prumer_cekani) \
        .order_by(Kraj.nazev, Okres.nazev, OckovaciMisto.nazev) \
        .all()

    return centers


def count_vaccines_center(center_id):
    mista = pd.read_sql_query(
        """
        select ockovaci_mista.id ockovaci_misto_id, ockovaci_mista.nazev, okres_id, kraj_id 
        from ockovaci_mista join okresy on ockovaci_mista.okres_id=okresy.id
        where ockovaci_mista.id='{}';
        """.format(center_id),
        db.engine
    )

    prijato = pd.read_sql_query(
        """
        select ockovaci_misto_id, vyrobce, sum(pocet_davek) prijato
        from ockovani_distribuce 
        where akce = 'Příjem' and ockovaci_misto_id = '{}' and datum < '{}'
        group by (ockovaci_misto_id, vyrobce);
        """.format(center_id, get_import_date()),
        db.engine
    )

    prijato_odjinud = pd.read_sql_query(
        """
        select cilove_ockovaci_misto_id ockovaci_misto_id, vyrobce, sum(pocet_davek) prijato_odjinud
        from ockovani_distribuce 
        where akce = 'Výdej' and cilove_ockovaci_misto_id = '{}' and datum < '{}'
        group by (cilove_ockovaci_misto_id, vyrobce);
        """.format(center_id, get_import_date()),
        db.engine
    )

    vydano = pd.read_sql_query(
        """
        select ockovaci_misto_id, vyrobce, sum(pocet_davek) vydano
        from ockovani_distribuce 
        where akce = 'Výdej' and ockovaci_misto_id = '{}' and datum < '{}'  
        group by (ockovaci_misto_id, vyrobce);
        """.format(center_id, get_import_date()),
        db.engine
    )

    spotreba = pd.read_sql_query(
        """
        select ockovaci_misto_id, vyrobce, sum(pouzite_davky) pouzito, sum(znehodnocene_davky) znehodnoceno
        from ockovani_spotreba 
        where ockovaci_misto_id = '{}' and datum < '{}'
        group by (ockovaci_misto_id, vyrobce);
        """.format(center_id, get_import_date()),
        db.engine
    )

    vyrobci = pd.read_sql_query(
        """
        select distinct(vyrobce)
        from ockovani_distribuce;
        """,
        db.engine
    )

    mista_key = mista
    mista_key['join'] = 0
    vyrobci_key = vyrobci
    vyrobci_key['join'] = 0

    res = mista_key.merge(vyrobci_key).drop('join', axis=1)

    res = pd.merge(res, prijato, how="left")
    res = pd.merge(res, prijato_odjinud, how="left")
    res = pd.merge(res, vydano, how="left")
    res = pd.merge(res, spotreba, how="left")

    res['prijato'] = res['prijato'].fillna(0).astype('int')
    res['prijato_odjinud'] = res['prijato_odjinud'].fillna(0).astype('int')
    res['vydano'] = res['vydano'].fillna(0).astype('int')
    res['pouzito'] = res['pouzito'].fillna(0).astype('int')
    res['znehodnoceno'] = res['znehodnoceno'].fillna(0).astype('int')

    res['prijato_celkem'] = res['prijato'] + res['prijato_odjinud'] - res['vydano']
    res['skladem'] = res['prijato_celkem'] - res['pouzito'] - res['znehodnoceno']

    res = res.groupby(by=['vyrobce'], as_index=False).sum().sort_values(by=['vyrobce'])

    return res


def count_vaccines_kraj(kraj_id):
    mista = pd.read_sql_query(
        """
        select ockovaci_mista.id ockovaci_misto_id, ockovaci_mista.nazev, kraj_id 
        from ockovaci_mista join okresy on ockovaci_mista.okres_id=okresy.id
        where kraj_id='{}';
        """.format(kraj_id),
        db.engine
    )
    mista_ids = ','.join("'" + misto + "'" for misto in mista['ockovaci_misto_id'].tolist())

    prijato = pd.read_sql_query(
        """
        select ockovaci_misto_id, vyrobce, sum(pocet_davek) prijato
        from ockovani_distribuce 
        where akce = 'Příjem' and ockovaci_misto_id in ({}) and datum < '{}'
        group by (ockovaci_misto_id, vyrobce);
        """.format(mista_ids, get_import_date()),
        db.engine
    )

    prijato_odjinud = pd.read_sql_query(
        """
        select cilove_ockovaci_misto_id ockovaci_misto_id, vyrobce, sum(pocet_davek) prijato_odjinud
        from ockovani_distribuce 
        where akce = 'Výdej' and cilove_ockovaci_misto_id in ({}) and ockovaci_misto_id not in({}) and datum < '{}'
        group by (cilove_ockovaci_misto_id, vyrobce);
        """.format(mista_ids, mista_ids, get_import_date()),
        db.engine
    )

    vydano = pd.read_sql_query(
        """
        select ockovaci_misto_id, vyrobce, sum(pocet_davek) vydano
        from ockovani_distribuce 
        where akce = 'Výdej' and ockovaci_misto_id in ({}) and cilove_ockovaci_misto_id not in({}) and cilove_ockovaci_misto_id != '' and datum < '{}'  
        group by (ockovaci_misto_id, vyrobce);
        """.format(mista_ids, mista_ids, get_import_date()),
        db.engine
    )

    spotreba = pd.read_sql_query(
        """
        select ockovaci_misto_id, vyrobce, sum(znehodnocene_davky) znehodnoceno
        from ockovani_spotreba 
        where ockovaci_misto_id in ({}) and datum < '{}'
        group by (ockovaci_misto_id, vyrobce);
        """.format(mista_ids, get_import_date()),
        db.engine
    )

    ockovano = pd.read_sql_query(
        """
        select kraj_nuts_kod kraj_id, sum(pocet) ockovano,
            case 
                when vakcina = 'COVID-19 Vaccine AstraZeneca' then 'AstraZeneca'
                when vakcina = 'COVID-19 Vaccine Moderna' then 'Moderna'
                when vakcina = 'Comirnaty' then 'Pfizer'
            else 'ostatní' end vyrobce
        from ockovani_lide
        where kraj_nuts_kod = '{}' and datum < '{}'
        group by kraj_nuts_kod, vakcina
        """.format(kraj_id, get_import_date()),
        db.engine
    )

    vyrobci = pd.read_sql_query(
        """
        select distinct(vyrobce)
        from ockovani_distribuce;
        """,
        db.engine
    )

    mista_key = mista
    mista_key['join'] = 0
    vyrobci_key = vyrobci
    vyrobci_key['join'] = 0

    res = mista_key.merge(vyrobci_key).drop('join', axis=1)

    res = pd.merge(res, prijato, how="left")
    res = pd.merge(res, prijato_odjinud, how="left")
    res = pd.merge(res, vydano, how="left")
    res = pd.merge(res, spotreba, how="left")

    res['prijato'] = res['prijato'].fillna(0).astype('int')
    res['prijato_odjinud'] = res['prijato_odjinud'].fillna(0).astype('int')
    res['vydano'] = res['vydano'].fillna(0).astype('int')
    res['znehodnoceno'] = res['znehodnoceno'].fillna(0).astype('int')

    res = res.groupby(by=['kraj_id', 'vyrobce'], as_index=False).sum()

    res = pd.merge(res, ockovano, how="left")

    res['ockovano'] = res['ockovano'].fillna(0).astype('int')

    res['prijato_celkem'] = res['prijato'] + res['prijato_odjinud'] - res['vydano']
    res['skladem'] = res['prijato_celkem'] - res['ockovano'] - res['znehodnoceno']

    res = res.groupby(by=['vyrobce'], as_index=False).sum().sort_values(by=['vyrobce'])

    return res


def count_vaccines_cr():
    prijato = pd.read_sql_query(
        """
        select vyrobce, sum(pocet_davek) prijato
        from ockovani_distribuce
        where akce = 'Příjem' and datum < '{}'
        group by (vyrobce);
        """.format(get_import_date()),
        db.engine
    )

    spotreba = pd.read_sql_query(
        """
        select vyrobce, sum(znehodnocene_davky) znehodnoceno
        from ockovani_spotreba 
        where datum < '{}'
        group by (vyrobce);
        """.format(get_import_date()),
        db.engine
    )

    ockovano = pd.read_sql_query(
        """
        select sum(pocet) ockovano,
            case 
                when vakcina = 'COVID-19 Vaccine AstraZeneca' then 'AstraZeneca'
                when vakcina = 'COVID-19 Vaccine Moderna' then 'Moderna'
                when vakcina = 'Comirnaty' then 'Pfizer'
                else 'ostatní' end vyrobce
        from ockovani_lide
        where datum < '{}'
        group by vakcina
        """.format(get_import_date()),
        db.engine
    )

    res = pd.merge(prijato, spotreba, how="left")

    res['prijato'] = res['prijato'].fillna(0).astype('int')
    res['znehodnoceno'] = res['znehodnoceno'].fillna(0).astype('int')

    res = res.groupby(by=['vyrobce'], as_index=False).sum()

    res = pd.merge(res, ockovano, how="left")

    res['ockovano'] = res['ockovano'].fillna(0).astype('int')

    res['prijato_celkem'] = res['prijato']
    res['skladem'] = res['prijato_celkem'] - res['ockovano'] - res['znehodnoceno']

    res = res.groupby(by=['vyrobce'], as_index=False).sum().sort_values(by=['vyrobce'])

    return res


def count_registrations(filter_column, filter_value):
    mista = pd.read_sql_query(
        """
        select ockovaci_mista.id ockovaci_misto_id from ockovaci_mista join okresy on ockovaci_mista.okres_id=okresy.id
        where {}='{}';
        """.format(filter_column, filter_value),
        db.engine
    )
    mista_ids = ','.join("'" + misto + "'" for misto in mista['ockovaci_misto_id'].tolist())

    df = pd.read_sql_query(
        """
        select *
        from ockovani_registrace
        where import_id = {} and ockovaci_misto_id in({})
        """.format(get_import_id(), mista_ids),
        db.engine
    )

    if df.empty:
        return df

    df['dnes'] = get_import_date()
    df['datum_rezervace_fix'] = df['datum_rezervace'].where(df['datum_rezervace'] != date(1970, 1, 1))
    df['fronta_pocet'] = df[['pocet']].where(df['rezervace'] == False).fillna(0).astype('int')
    df['fronta_cekani'] = (df['dnes'] - df['datum']).astype('timedelta64[ns]').dt.days
    df['fronta_pocet_x_cekani'] = df['fronta_pocet'] * df['fronta_cekani']
    df['registrace_7'] = df[['pocet']].where(df['datum'] >= get_import_date() - timedelta(7))
    df['registrace_7_rez'] = df[['pocet']].where((df['rezervace'] == True) & (df['datum'] >= get_import_date() - timedelta(7)))
    # df['registrace_14'] = df[['pocet']].where(df['datum'] >= get_import_date() - timedelta(14))
    # df['registrace_14_rez'] = df[['pocet']].where((df['rezervace'] == True) & (df['datum'] >= get_import_date() - timedelta(14)))
    # df['registrace_30'] = df[['pocet']].where(df['datum'] >= get_import_date() - timedelta(30))
    # df['registrace_30_rez'] = df[['pocet']].where((df['rezervace'] == True) & (df['datum'] >= get_import_date() - timedelta(30)))
    df['rezervace_7_cekani'] = (df['datum_rezervace_fix'] - df['datum']).astype('timedelta64[ns]').dt.days
    df['rezervace_7_pocet'] = df[['pocet']].where((df['rezervace'] == True) & (df['datum_rezervace_fix'] >= get_import_date() - timedelta(7)))
    df['rezervace_7_pocet_x_cekani'] = df['rezervace_7_cekani'] * df['rezervace_7_pocet']

    df = df.groupby(['vekova_skupina', 'povolani']).sum()

    df['uspesnost_7'] = ((df['registrace_7_rez'] / df['registrace_7']) * 100).replace({np.nan: None})
    # df['uspesnost_14'] = ((df['registrace_14_rez'] / df['registrace_14']) * 100).replace({np.nan: None})
    # df['uspesnost_30'] = ((df['registrace_30_rez'] / df['registrace_30']) * 100).replace({np.nan: None})
    df['registrace_7'] = df['registrace_7'].astype('int')
    df['registrace_7_rez'] = df['registrace_7_rez'].astype('int')
    # df['registrace_14'] = df['registrace_14'].astype('int')
    # df['registrace_14_rez'] = df['registrace_14_rez'].astype('int')
    # df['registrace_30'] = df['registrace_30'].astype('int')
    # df['registrace_30_rez'] = df['registrace_30_rez'].astype('int')
    df['fronta_prumer_cekani'] = ((df['fronta_pocet_x_cekani'] / df['fronta_pocet']) / 7).replace({np.nan: None})
    df['rezervace_prumer_cekani'] = ((df['rezervace_7_pocet_x_cekani'] / df['rezervace_7_pocet']) / 7).replace({np.nan: None})

    df = df[(df['fronta_pocet'] > 0) | df['fronta_prumer_cekani'].notnull() | df['rezervace_prumer_cekani'].notnull() | df['uspesnost_7'].notnull()]

    return df.reset_index().sort_values(by=['vekova_skupina', 'povolani'])


def count_vaccinated(kraj_id=None):
    ockovani = pd.read_sql_query(
        """
        select vekova_skupina, vakcina, poradi_davky, sum(pocet) pocet_ockovani
        from ockovani_lide
        where datum < '{}' and (kraj_nuts_kod = '{}' or {})
        group by vekova_skupina, vakcina, poradi_davky
        """.format(get_import_date(), kraj_id, kraj_id is None),
        db.engine
    )

    if kraj_id is not None:
        mista = pd.read_sql_query(
            """
            select ockovaci_mista.id ockovaci_misto_id from ockovaci_mista join okresy on ockovaci_mista.okres_id=okresy.id
            where kraj_id='{}';
            """.format(kraj_id),
            db.engine
        )
        mista_ids = ','.join("'" + misto + "'" for misto in mista['ockovaci_misto_id'].tolist())
    else:
        mista_ids = "''"

    registrace = pd.read_sql_query(
        """
        select vekova_skupina, sum(pocet) pocet_fronta
        from ockovani_registrace
        where rezervace = false and import_id = {} and (ockovaci_misto_id in({}) or {})
        group by vekova_skupina
        """.format(get_import_id(), mista_ids, kraj_id is None),
        db.engine
    )

    populace = pd.read_sql_query(
        """
        select vekova_skupina, sum(pocet) pocet_vek
        from populace p 
        join populace_kategorie k on (k.min_vek <= vek and k.max_vek >= vek)
        where orp_kod = '{}'
        group by vekova_skupina
        """.format('CZ0' if kraj_id is None else kraj_id),
        db.engine
    )

    ockovani['vekova_skupina'] = ockovani['vekova_skupina'].replace(['nezařazeno'], 'neuvedeno')
    ockovani['pocet_ockovani_castecne'] = ockovani['pocet_ockovani'].where(ockovani['poradi_davky'] == 1).fillna(0).astype('int')
    ockovani['pocet_ockovani_plne'] = ockovani['pocet_ockovani'].where((ockovani['poradi_davky'] == 2) | (ockovani['vakcina'].isin([]))).fillna(0).astype('int')
    ockovani_grp = ockovani.groupby(['vekova_skupina']).sum().drop('poradi_davky', axis=1).reset_index()

    merged = pd.merge(ockovani_grp, registrace, how="left")
    merged = pd.merge(merged, populace, how="left")

    merged['podil_ockovani_castecne'] = (merged['pocet_ockovani_castecne'] / merged['pocet_vek']).replace({np.nan: None})
    merged['podil_ockovani_plne'] = (merged['pocet_ockovani_plne'] / merged['pocet_vek']).replace({np.nan: None})
    merged['pocet_fronta'] = merged['pocet_fronta'].fillna(0).astype('int')

    return merged


def get_registrations_graph_data(center_id):
    registrace = pd.read_sql_query(
        """
        select datum, sum(pocet) pocet_registrace
        from ockovani_registrace  
        where ockovaci_misto_id = '{}' and import_id = {}
        group by datum
        """.format(center_id, get_import_id()),
        db.engine
    )

    rezervace = pd.read_sql_query(
        """
        select datum_rezervace datum, sum(pocet) pocet_rezervace
        from ockovani_registrace  
        where ockovaci_misto_id = '{}' and import_id = {} and rezervace = true
        group by datum_rezervace
        """.format(center_id, get_import_id()),
        db.engine
    )

    merged = pd.merge(registrace, rezervace, how='outer')

    if merged.empty:
        return merged

    return merged.set_index('datum').asfreq('D').fillna(0).sort_values('datum')


def get_queue_graph_data(center_id):
    fronta = pd.read_sql_query(
        """
        select datum, registrace_fronta, rezervace_cekajici_1, rezervace_cekajici_2
        from ockovaci_mista_metriky
        where misto_id = '{}'
        """.format(center_id),
        db.engine
    )

    fronta = fronta.set_index('datum').fillna(0).sort_values('datum')

    for idx, row in fronta.iterrows():
        if row['registrace_fronta'] == 0 and row['rezervace_cekajici_1'] == 0 and row['rezervace_cekajici_2'] == 0:
            fronta.drop(idx, inplace=True)
        else:
            break

    return fronta
