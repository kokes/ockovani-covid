from datetime import timedelta, datetime

from flask import render_template
from sqlalchemy import func, text
from werkzeug.exceptions import abort

from app import db, bp, filters, queries
from app.context import get_import_date, get_import_id, STATUS_FINISHED
from app.models import Import, Okres, Kraj, OckovaciMisto, OckovaciMistoMetriky, KrajMetriky, OkresMetriky, CrMetriky, \
    Vakcinacka


@bp.route('/')
def index():
    return render_template('index.html', last_update=_last_import_modified(), now=_now())


@bp.route("/mista")
def info_mista():
    mista = queries.find_centers(True, True)

    return render_template('mista.html', mista=mista, last_update=_last_import_modified(), now=_now())


@bp.route("/okres/<okres_name>")
def info_okres(okres_name):
    okres = db.session.query(Okres).filter(Okres.nazev == okres_name).one_or_none()
    if okres is None:
        abort(404)

    mista = queries.find_centers(Okres.id, okres.id)

    metriky = db.session.query(OkresMetriky) \
        .filter(OkresMetriky.okres_id == okres.id, OkresMetriky.datum == get_import_date()) \
        .one_or_none()

    registrations = queries.count_registrations('okres_id', okres.id)

    return render_template('okres.html', last_update=_last_import_modified(), now=_now(), okres=okres, metriky=metriky,
                           mista=mista, registrations=registrations)


@bp.route("/kraj/<kraj_name>")
def info_kraj(kraj_name):
    kraj = db.session.query(Kraj).filter(Kraj.nazev == kraj_name).one_or_none()
    if kraj is None:
        abort(404)

    mista = queries.find_centers(Kraj.id, kraj.id)

    metriky = db.session.query(KrajMetriky) \
        .filter(KrajMetriky.kraj_id == kraj.id, KrajMetriky.datum == get_import_date()) \
        .one_or_none()

    registrations = queries.count_registrations('kraj_id', kraj.id)

    vaccines = queries.count_vaccines_kraj(kraj.id)

    vaccinated = queries.count_vaccinated(kraj.id)

    vaccination_doctors = queries.count_vaccinated_doctors(kraj.id)

    queue_graph_data = queries.get_queue_graph_data(kraj_id=kraj.id)

    return render_template('kraj.html', last_update=_last_import_modified(), now=_now(), kraj=kraj, metriky=metriky,
                           mista=mista, vaccines=vaccines, registrations=registrations, vaccinated=vaccinated,
                           vaccination_doctors=vaccination_doctors,
                           queue_graph_data=queue_graph_data)


@bp.route("/misto/<misto_id>")
def info_misto(misto_id):
    misto = db.session.query(OckovaciMisto).filter(OckovaciMisto.id == misto_id).one_or_none()
    if misto is None:
        abort(404)

    metriky = db.session.query(OckovaciMistoMetriky) \
        .filter(OckovaciMistoMetriky.misto_id == misto_id, OckovaciMistoMetriky.datum == get_import_date()) \
        .one_or_none()

    registrations = queries.count_registrations('ockovaci_mista.id', misto_id)

    free_slots = queries.count_free_slots(misto_id)

    vaccines = queries.count_vaccines_center(misto_id)

    queue_graph_data = queries.get_queue_graph_data(center_id=misto_id)

    registrations_graph_data = queries.get_registrations_graph_data(misto_id)

    vaccination_graph_data = queries.get_vaccination_graph_data(misto_id)

    return render_template('misto.html', last_update=_last_import_modified(), now=_now(), misto=misto, metriky=metriky,
                           vaccines=vaccines, registrations=registrations, free_slots=free_slots,
                           queue_graph_data=queue_graph_data, registrations_graph_data=registrations_graph_data,
                           vaccination_graph_data=vaccination_graph_data)


@bp.route("/mapa")
def mapa():
    mista = queries.find_centers(OckovaciMisto.status, True)

    return render_template('mapa.html', last_update=_last_import_modified(), now=_now(), mista=mista)


@bp.route("/praktici")
def praktici():
    vaccination_doctors = queries.count_vaccinated_doctors()

    return render_template('praktici.html', last_update=_last_import_modified(), now=_now(),
                           vaccination_doctors=vaccination_doctors)


@bp.route("/statistiky")
def statistiky():
    metriky = db.session.query(CrMetriky) \
        .filter(CrMetriky.datum == get_import_date()) \
        .one_or_none()

    end_date = queries.count_end_date_vaccinated()

    end_date_supplies = queries.count_end_date_supplies()

    end_date_interested = queries.couht_end_date_interested()

    vaccines = queries.count_vaccines_cr()

    vaccinated = queries.count_vaccinated()

    supplies = queries.count_supplies()

    end_date_category = queries.count_end_date_category()

    vaccinated_category = queries.count_vaccinated_category()

    reservations_category = queries.count_reservations_category()

    vaccinated_week = queries.count_vaccinated_week()

    top_centers = queries.count_top_centers()

    # Source data for graph of received vaccines of the manufacturers
    received_vaccine_graph_data = queries.get_received_vaccine_graph_data()

    # Source data for graph of used vaccines based on the manufacturers
    used_vaccine_graph_data = queries.get_used_vaccine_graph_data()

    # Source data for graph of people in queue for the whole republic
    queue_graph_data = queries.get_queue_graph_data()

    vaccination_total_graph_data = queries.get_vaccination_total_graph_data()

    registrations_graph_data = queries.get_registrations_graph_data()

    infected_graph_data = queries.get_infected_graph_data()

    deaths_graph_data = queries.get_deaths_graph_data()

    return render_template('statistiky.html', last_update=_last_import_modified(), now=_now(), metriky=metriky,
                           end_date=end_date, end_date_supplies=end_date_supplies,
                           end_date_interested=end_date_interested, vaccines=vaccines, vaccinated=vaccinated,
                           vaccinated_category=vaccinated_category, reservations_category=reservations_category,
                           supplies=supplies, end_date_category=end_date_category,
                           vaccinated_week=vaccinated_week, top_centers=top_centers,
                           received_vaccine_graph_data=received_vaccine_graph_data,
                           used_vaccine_graph_data=used_vaccine_graph_data, queue_graph_data=queue_graph_data,
                           vaccination_total_graph_data=vaccination_total_graph_data,
                           registrations_graph_data=registrations_graph_data,
                           infected_graph_data=infected_graph_data, deaths_graph_data=deaths_graph_data)


@bp.route("/napoveda")
def napoveda():
    return render_template('napoveda.html', last_update=_last_import_modified(), now=_now())


@bp.route("/odkazy")
def odkazy():
    return render_template('odkazy.html', last_update=_last_import_modified(), now=_now())


@bp.route("/dataquality")
def dataquality():
    susp_vaccination_type = db.session.query("datum", "vakcina", "zarizeni_kod", "zarizeni_nazev", "vekova_skupina",
                                             "pocet").from_statement(text(
        """
        select datum, vakcina, zarizeni_kod, zarizeni_nazev, vekova_skupina, pocet 
        from ockovani_lide where vakcina not in ('Comirnaty','VAXZEVRIA','COVID-19 Vaccine Moderna', 'COVID-19 Vaccine Janssen')
        """
    )).all()

    susp_vaccination_age = db.session.query("datum", "vakcina", "zarizeni_kod", "zarizeni_nazev", "vekova_skupina",
                                            "pocet").from_statement(text(
        """
        select datum, vakcina, zarizeni_kod, zarizeni_nazev, vekova_skupina, pocet 
        from ockovani_lide where vakcina !='Comirnaty' and vekova_skupina='0-17'
        """
    )).all()

    susp_storage_vacc = db.session.query("pomer", "vakciny_skladem_pocet", "ockovani_pocet_davek",
                                         "nazev").from_statement(text(
        """
        select ockovani_pocet_davek/vakciny_skladem_pocet pomer,vakciny_skladem_pocet, ockovani_pocet_davek, om.nazev from ockovaci_mista_metriky omm
            join ockovaci_mista om on (omm.misto_id=om.id)
            where vakciny_skladem_pocet>200 and (ockovani_pocet_davek*1.0/vakciny_skladem_pocet<0.15)
            and omm.datum+'2 day'::interval>'{}'
        """.format(get_import_date())
    )).all()

    susp_vaccination = db.session.query("vakciny_prijate_pocet", "ockovani_pocet_davek", "nazev").from_statement(text(
        """
        select vakciny_prijate_pocet, ockovani_pocet_davek, om.nazev from ockovaci_mista_metriky omm
            join ockovaci_mista om on (omm.misto_id=om.id)
            where vakciny_prijate_pocet>10 and (ockovani_pocet_davek*1.0/vakciny_prijate_pocet<0.15)
            and omm.datum+'1 day'::interval>'{}'
        """.format(get_import_date())
    )).all()

    susp_vaccination_accepted = db.session.query("vakciny_prijate_pocet", "ockovani_pocet_davek",
                                                 "nazev").from_statement(text(
        """
        select vakciny_prijate_pocet, ockovani_pocet_davek, om.nazev from ockovaci_mista_metriky omm
            join ockovaci_mista om on (omm.misto_id=om.id)
            where vakciny_prijate_pocet>10 and (ockovani_pocet_davek*1.0/vakciny_prijate_pocet>2)
            and omm.datum+'1 day'::interval>'{}'
        """.format(get_import_date())
    )).all()

    susp_reservation_vaccination = db.session.query("nazev", "nrpzs_kod", "sum30_mimo_rezervace").from_statement(text(
        """
        select nazev, nrpzs_kod, sum( ockovani-pocet_rezervaci) sum30_mimo_rezervace
            from (
            select om.nazev, rez.nrpzs_kod, rez.datum, rez.pocet_rezervaci, ocko.ockovani, round(ockovani*1.0/pocet_rezervaci, 2) pomer from (
                        select ocm.nrpzs_kod, o.datum, sum(maximalni_kapacita-volna_kapacita) pocet_rezervaci 
                        from ockovani_rezervace o join ockovaci_mista ocm on (o.ockovaci_misto_id=ocm.id)
                        where import_id={} and o.datum<now() group by ocm.nrpzs_kod, o.datum) rez join (
                        select datum, zarizeni_kod, sum(pocet) ockovani from ockovani_lide 
                        group by datum, zarizeni_kod) ocko on (rez.nrpzs_kod=ocko.zarizeni_kod and rez.datum=ocko.datum)
                        join (select min(nazev) nazev, nrpzs_kod from ockovaci_mista group by nrpzs_kod) om on (om.nrpzs_kod=ocko.zarizeni_kod)
                        where pocet_rezervaci>0 and ockovani*1.0/pocet_rezervaci>=2
                        and rez.datum+'31 days'::interval>'{}' and ockovani>100
                        --order by round(ockovani*1.0/pocet_rezervaci, 2) desc
            ) pomery group by nazev, nrpzs_kod order by sum( ockovani-pocet_rezervaci) desc
        """.format(get_import_id(), get_import_date())
    )).all()

    susp_reservation_vaccination_low = db.session.query("nazev", "nrpzs_kod", "datum", "pocet_rezervaci", "ockovani",
                                                        "pomer").from_statement(text(
        """
        select om.nazev, rez.nrpzs_kod, rez.datum, rez.pocet_rezervaci, ocko.ockovani, round(ockovani*1.0/pocet_rezervaci, 2) pomer from (
            select ocm.nrpzs_kod, o.datum, sum(maximalni_kapacita-volna_kapacita) pocet_rezervaci 
            from ockovani_rezervace o join ockovaci_mista ocm on (o.ockovaci_misto_id=ocm.id)
            where import_id={} and o.datum<now() group by ocm.nrpzs_kod, o.datum) rez join (
            select datum, zarizeni_kod, sum(pocet) ockovani from ockovani_lide 
            group by datum, zarizeni_kod) ocko on (rez.nrpzs_kod=ocko.zarizeni_kod and rez.datum=ocko.datum)
            join (select min(nazev) nazev, nrpzs_kod from ockovaci_mista group by nrpzs_kod) om on (om.nrpzs_kod=ocko.zarizeni_kod)
            where pocet_rezervaci>100 and ockovani*1.0/pocet_rezervaci<0.3
            and rez.datum+'31 days'::interval>'{}'  
            order by round(ockovani*1.0/pocet_rezervaci, 2) desc
        """.format(get_import_id(), get_import_date())
    )).all()

    return render_template('dataquality.html', last_update=_last_import_modified(), now=_now(),
                           susp_vaccination_type=susp_vaccination_type,
                           vaccinated_age=susp_vaccination_age, susp_storage_vacc=susp_storage_vacc,
                           susp_vaccination=susp_vaccination,
                           susp_vaccination_accepted=susp_vaccination_accepted,
                           susp_reservation_vaccination=susp_reservation_vaccination,
                           susp_reservation_vaccination_low=susp_reservation_vaccination_low)


def _last_import_modified():
    """
    Returns last successful import.
    """
    last_modified = db.session.query(func.max(Import.last_modified)) \
        .filter(Import.status == STATUS_FINISHED) \
        .first()[0]
    return 'nikdy' if last_modified is None else filters.format_datetime_short_wd(last_modified)


def _now():
    return filters.format_datetime_short_wd(datetime.now())
