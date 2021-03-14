from datetime import timedelta, date

from sqlalchemy import func, case, text, or_, and_

from app import db, app, queries
from app.models import OckovaciMisto, OckovaciMistoMetriky, OckovaniRegistrace, OckovaniRezervace, Import, \
    OckovaniLide, OckovaniDistribuce, OckovaniSpotreba, Okres, OkresMetriky, Kraj, KrajMetriky, Populace


class Etl:
    def __init__(self, date_):
        self._date = date_
        self._import_id = self._find_import_id()

    def compute_all(self):
        try:
            self.compute_center()
            self.compute_okres()
            self.compute_regions()
        except Exception as e:
            app.logger.error(e)
            db.session.rollback()
            return False

        db.session.commit()
        return True

    def compute_center(self):
        self._compute_center_registrations()
        self._compute_center_reservations()
        self._compute_center_vaccinated()
        self._compute_center_distributed()
        self._compute_center_used()
        self._compute_center_derived()
        self._compute_center_deltas()

    def compute_okres(self):
        self._compute_okres_population()
        self._compute_okres_registrations()
        self._compute_okres_reservations()
        # # self._compute_okres_vaccinated() # todo
        self._compute_okres_distributed()
        self._compute_okres_used()
        self._compute_okres_derived()
        self._compute_okres_deltas()

    def compute_regions(self):
        self._compute_kraj_population()
        self._compute_kraj_registrations()
        self._compute_kraj_reservations()
        self._compute_kraj_vaccinated()
        self._compute_kraj_distributed()
        self._compute_kraj_used()
        self._compute_kraj_derived()
        self._compute_kraj_deltas()

    def _compute_center_registrations(self):
        """Computes metrics based on registrations dataset for each vaccination center."""
        registrations = db.session.query(
            OckovaciMisto.id, func.coalesce(func.sum(OckovaniRegistrace.pocet), 0).label('registrace_celkem'),
            func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == False, OckovaniRegistrace.pocet)], else_=0)), 0).label("registrace_fronta")
        ).outerjoin(OckovaniRegistrace, and_(OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id, OckovaniRegistrace.import_id == self._import_id)) \
            .group_by(OckovaciMisto.id) \
            .all()

        for registration in registrations:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=registration.id,
                datum=self._date,
                registrace_celkem=registration.registrace_celkem,
                registrace_fronta=registration.registrace_fronta
            ))

        app.logger.info('Computing vaccination centers metrics - registrations finished.')

    def _compute_center_reservations(self):
        """Computes metrics based on reservations dataset for each vaccination center."""
        reservations = db.session.query(
            OckovaciMisto.id,
            func.coalesce(func.sum(OckovaniRezervace.maximalni_kapacita - OckovaniRezervace.volna_kapacita), 0).label('rezervace_celkem'),
            func.coalesce(func.sum(case([(OckovaniRezervace.datum >= self._date, OckovaniRezervace.maximalni_kapacita - OckovaniRezervace.volna_kapacita)], else_=0)), 0).label("rezervace_cekajici")
        ).outerjoin(OckovaniRezervace, and_(OckovaciMisto.id == OckovaniRezervace.ockovaci_misto_id, OckovaniRezervace.import_id == self._import_id)) \
            .group_by(OckovaciMisto.id) \
            .all()

        for reservation in reservations:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=reservation.id,
                datum=self._date,
                rezervace_celkem=reservation.rezervace_celkem,
                rezervace_cekajici=reservation.rezervace_cekajici
            ))

        app.logger.info('Computing vaccination centers metrics - reservations finished.')

    def _compute_center_vaccinated(self):
        """Computes metrics based on vaccinated people dataset for each vaccination center."""
        vaccinated = db.session.query(OckovaciMisto.id, func.coalesce(func.sum(OckovaniLide.pocet), 0).label('ockovani_pocet'),
                                      func.coalesce(func.sum(case([(OckovaniLide.poradi_davky == 1, OckovaniLide.pocet)], else_=0)), 0).label('ockovani_pocet_1'),
                                      func.coalesce(func.sum(case([(OckovaniLide.poradi_davky == 2, OckovaniLide.pocet)], else_=0)), 0).label('ockovani_pocet_2')) \
            .outerjoin(OckovaniLide, and_(OckovaciMisto.nrpzs_kod == OckovaniLide.zarizeni_kod, OckovaniLide.datum < self._date)) \
            .filter(OckovaciMisto.nrpzs_kod.in_(queries.unique_nrpzs_subquery())) \
            .group_by(OckovaciMisto.id) \
            .all()

        for vacc in vaccinated:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=vacc.id,
                datum=self._date,
                ockovani_pocet=vacc.ockovani_pocet,
                ockovani_pocet_1=vacc.ockovani_pocet_1,
                ockovani_pocet_2=vacc.ockovani_pocet_2
            ))

        app.logger.info('Computing vaccination centers metrics - vaccinated people finished.')

    def _compute_center_distributed(self):
        """Computes metrics based on distributed vaccines dataset for each vaccination center."""
        distributed = db.session.query(
            OckovaciMisto.id,
            func.coalesce(func.sum(case([(and_(OckovaciMisto.id == OckovaniDistribuce.ockovaci_misto_id, OckovaniDistribuce.akce == 'Výdej'), 0)], else_=OckovaniDistribuce.pocet_davek)), 0).label('vakciny_prijate_pocet'),
            func.coalesce(func.sum(case([(and_(OckovaciMisto.id == OckovaniDistribuce.ockovaci_misto_id, OckovaniDistribuce.akce == 'Výdej'), OckovaniDistribuce.pocet_davek)], else_=0)), 0).label('vakciny_vydane_pocet')
        ).outerjoin(OckovaniDistribuce,
               and_(
                   or_(
                       and_(OckovaciMisto.id == OckovaniDistribuce.ockovaci_misto_id, or_(OckovaniDistribuce.akce == 'Příjem', OckovaniDistribuce.akce == 'Výdej')),
                       and_(OckovaciMisto.id == OckovaniDistribuce.cilove_ockovaci_misto_id, OckovaniDistribuce.akce == 'Výdej')
                   ),
                   OckovaniDistribuce.datum < self._date
               )) \
            .group_by(OckovaciMisto.id) \
            .all()

        for dist in distributed:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=dist.id,
                datum=self._date,
                vakciny_prijate_pocet=dist.vakciny_prijate_pocet,
                vakciny_vydane_pocet=dist.vakciny_vydane_pocet
            ))

        app.logger.info('Computing vaccination centers metrics - distributed vaccines finished.')

    def _compute_center_used(self):
        """Computes metrics based on used vaccines dataset for each vaccination center."""
        used = db.session.query(
            OckovaciMisto.id,
            func.coalesce(func.sum(OckovaniSpotreba.pouzite_davky), 0).label('vakciny_ockovane_pocet'),
            func.coalesce(func.sum(OckovaniSpotreba.znehodnocene_davky), 0).label('vakciny_znicene_pocet')
        ).outerjoin(OckovaniSpotreba, and_(OckovaciMisto.id == OckovaniSpotreba.ockovaci_misto_id, OckovaniSpotreba.datum < self._date)) \
            .group_by(OckovaciMisto.id) \
            .all()

        for use in used:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=use.id,
                datum=self._date,
                vakciny_ockovane_pocet=use.vakciny_ockovane_pocet,
                vakciny_znicene_pocet=use.vakciny_znicene_pocet
            ))

        app.logger.info('Computing vaccination centers metrics - used vaccines finished.')

    def _compute_center_derived(self):
        """Computes metrics derived from the previous metrics for each vaccination center."""
        avg_waiting = db.session.query(
            OckovaciMisto.id,
            func.avg(OckovaniRegistrace.datum_rezervace - OckovaniRegistrace.datum).label('registrace_prumer_cekani'),
        ).join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum_rezervace >= self._date - timedelta(7)) \
            .group_by(OckovaciMisto.id) \
            .all()

        for wait in avg_waiting:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=wait.id,
                datum=self._date,
                registrace_prumer_cekani=wait.registrace_prumer_cekani
            ))

        est_waiting = db.session.query("id", "registrace_odhad_cekani").from_statement(text(
            """
            select id, 7.0 * sum(case when rezervace = false then pocet else 0 end) 
                / nullif(sum(case when rezervace = true and datum_rezervace >= :datum_7 then pocet else 0 end), 0)
                 registrace_odhad_cekani
            from ockovaci_mista
            join ockovani_registrace on id = ockovaci_misto_id
            where import_id = :import_id
            group by (id)
            """
        )).params(datum_7=self._date - timedelta(7), import_id=self._import_id) \
            .all()

        for wait in est_waiting:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=wait.id,
                datum=self._date,
                registrace_odhad_cekani=wait.registrace_odhad_cekani
            ))

        success_ratio_7 = db.session.query(
            OckovaciMisto.id,
            (1.0 * func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == True, OckovaniRegistrace.pocet)], else_=0)), 0)
             / case([(func.sum(OckovaniRegistrace.pocet) == 0, None)], else_=func.sum(OckovaniRegistrace.pocet))).label('registrace_tydenni_uspesnost')
        ).join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum >= self._date - timedelta(7)) \
            .group_by(OckovaciMisto.id) \
            .all()

        for ratio in success_ratio_7:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=ratio.id,
                datum=self._date,
                registrace_tydenni_uspesnost=ratio.registrace_tydenni_uspesnost
            ))

        success_ratio_14 = db.session.query(
            OckovaciMisto.id,
            (1.0 * func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == True, OckovaniRegistrace.pocet)], else_=0)), 0)
             / case([(func.sum(OckovaniRegistrace.pocet) == 0, None)], else_=func.sum(OckovaniRegistrace.pocet))).label('registrace_14denni_uspesnost')
        ).join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum >= self._date - timedelta(14)) \
            .group_by(OckovaciMisto.id) \
            .all()

        for ratio in success_ratio_14:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=ratio.id,
                datum=self._date,
                registrace_14denni_uspesnost=ratio.registrace_14denni_uspesnost
            ))

        success_ratio_30 = db.session.query(
            OckovaciMisto.id,
            (1.0 * func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == True, OckovaniRegistrace.pocet)], else_=0)), 0)
             / case([(func.sum(OckovaniRegistrace.pocet) == 0, None)], else_=func.sum(OckovaniRegistrace.pocet))).label('registrace_30denni_uspesnost')
        ).join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum >= self._date - timedelta(30)) \
            .group_by(OckovaciMisto.id) \
            .all()

        for ratio in success_ratio_30:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=ratio.id,
                datum=self._date,
                registrace_30denni_uspesnost=ratio.registrace_30denni_uspesnost
            ))

        vacc_est_waiting = db.session.query(
            OckovaciMisto.id,
            (7.0 * (OckovaciMistoMetriky.registrace_fronta + OckovaciMistoMetriky.rezervace_cekajici)
             / case([(func.sum(OckovaniLide.pocet) > 0, func.sum(OckovaniLide.pocet))], else_=None)).label('ockovani_odhad_cekani')
        ).join(OckovaciMistoMetriky, OckovaciMisto.id == OckovaciMistoMetriky.misto_id) \
            .join(OckovaniLide, OckovaciMisto.nrpzs_kod == OckovaniLide.zarizeni_kod) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .filter(OckovaciMisto.nrpzs_kod.in_(queries.unique_nrpzs_subquery())) \
            .filter(OckovaniLide.datum < self._date, OckovaniLide.datum >= self._date - timedelta(7)) \
            .group_by(OckovaciMisto.id, OckovaciMistoMetriky.registrace_fronta, OckovaciMistoMetriky.rezervace_cekajici) \
            .all()

        for wait in vacc_est_waiting:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=wait.id,
                datum=self._date,
                ockovani_odhad_cekani=wait.ockovani_odhad_cekani
            ))

        vacc_skladem = db.session.query(
            OckovaciMisto.id, (OckovaciMistoMetriky.vakciny_prijate_pocet - OckovaciMistoMetriky.vakciny_vydane_pocet
                               - OckovaciMistoMetriky.ockovani_pocet - OckovaciMistoMetriky.vakciny_znicene_pocet).label('vakciny_skladem_pocet')
        ).join(OckovaciMistoMetriky, OckovaciMisto.id == OckovaciMistoMetriky.misto_id) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .group_by(OckovaciMisto.id, OckovaciMistoMetriky.vakciny_prijate_pocet,
                      OckovaciMistoMetriky.vakciny_vydane_pocet, OckovaciMistoMetriky.ockovani_pocet,
                      OckovaciMistoMetriky.vakciny_znicene_pocet) \
            .all()

        for vacc in vacc_skladem:
            db.session.merge(OckovaciMistoMetriky(
                misto_id=vacc.id,
                datum=self._date,
                vakciny_skladem_pocet=vacc.vakciny_skladem_pocet
            ))

        app.logger.info('Computing vaccination centers metrics - derived metrics finished.')

    def _compute_center_deltas(self):
        """Computes deltas for previous metrics for each vaccination center."""
        db.session.execute(text(
            """
            update ockovaci_mista_metriky t
            set rezervace_celkem_zmena_den = t0.rezervace_celkem - t1.rezervace_celkem,
                rezervace_cekajici_zmena_den = t0.rezervace_cekajici - t1.rezervace_cekajici,
                registrace_celkem_zmena_den = t0.registrace_celkem - t1.registrace_celkem,
                registrace_fronta_zmena_den = t0.registrace_fronta - t1.registrace_fronta,
                registrace_tydenni_uspesnost_zmena_den = t0.registrace_tydenni_uspesnost - t1.registrace_tydenni_uspesnost,
                registrace_14denni_uspesnost_zmena_den = t0.registrace_14denni_uspesnost - t1.registrace_14denni_uspesnost,
                registrace_30denni_uspesnost_zmena_den = t0.registrace_30denni_uspesnost - t1.registrace_30denni_uspesnost,
                registrace_prumer_cekani_zmena_den = t0.registrace_prumer_cekani - t1.registrace_prumer_cekani,
                registrace_odhad_cekani_zmena_den = t0.registrace_odhad_cekani - t1.registrace_odhad_cekani,
                ockovani_pocet_zmena_den = t0.ockovani_pocet - t1.ockovani_pocet,
                ockovani_pocet_1_zmena_den = t0.ockovani_pocet_1 - t1.ockovani_pocet_1,
                ockovani_pocet_2_zmena_den = t0.ockovani_pocet_2 - t1.ockovani_pocet_2,
                ockovani_odhad_cekani_zmena_den = t0.ockovani_odhad_cekani - t1.ockovani_odhad_cekani,
                vakciny_prijate_pocet_zmena_den = t0.vakciny_prijate_pocet - t1.vakciny_prijate_pocet,
                vakciny_vydane_pocet_zmena_den = t0.vakciny_vydane_pocet - t1.vakciny_vydane_pocet,
                vakciny_ockovane_pocet_zmena_den = t0.vakciny_ockovane_pocet - t1.vakciny_ockovane_pocet,
                vakciny_znicene_pocet_zmena_den = t0.vakciny_znicene_pocet - t1.vakciny_znicene_pocet,
                vakciny_skladem_pocet_zmena_den = t0.vakciny_skladem_pocet - t1.vakciny_skladem_pocet
            from ockovaci_mista_metriky t0 
            join ockovaci_mista_metriky t1
            on t0.misto_id = t1.misto_id
            where t.misto_id = t0.misto_id and t.datum = :datum and t0.datum = :datum and t1.datum = :datum_1  
            """
        ), {'datum': self._date, 'datum_1': self._date - timedelta(1)})

        db.session.execute(text(
            """
            update ockovaci_mista_metriky t
            set rezervace_celkem_zmena_tyden = t0.rezervace_celkem - t7.rezervace_celkem,
                rezervace_cekajici_zmena_tyden = t0.rezervace_cekajici - t7.rezervace_cekajici,
                registrace_celkem_zmena_tyden = t0.registrace_celkem - t7.registrace_celkem,
                registrace_fronta_zmena_tyden = t0.registrace_fronta - t7.registrace_fronta,
                registrace_tydenni_uspesnost_zmena_tyden = t0.registrace_tydenni_uspesnost - t7.registrace_tydenni_uspesnost,
                registrace_14denni_uspesnost_zmena_tyden = t0.registrace_14denni_uspesnost - t7.registrace_14denni_uspesnost,
                registrace_30denni_uspesnost_zmena_tyden = t0.registrace_30denni_uspesnost - t7.registrace_30denni_uspesnost,
                registrace_prumer_cekani_zmena_tyden = t0.registrace_prumer_cekani - t7.registrace_prumer_cekani,
                registrace_odhad_cekani_zmena_tyden = t0.registrace_odhad_cekani - t7.registrace_odhad_cekani,
                ockovani_pocet_zmena_tyden = t0.ockovani_pocet - t7.ockovani_pocet,
                ockovani_pocet_1_zmena_tyden = t0.ockovani_pocet_1 - t7.ockovani_pocet_1,
                ockovani_pocet_2_zmena_tyden = t0.ockovani_pocet_2 - t7.ockovani_pocet_2,
                ockovani_odhad_cekani_zmena_tyden = t0.ockovani_odhad_cekani - t7.ockovani_odhad_cekani,
                vakciny_prijate_pocet_zmena_tyden = t0.vakciny_prijate_pocet - t7.vakciny_prijate_pocet,
                vakciny_vydane_pocet_zmena_tyden = t0.vakciny_vydane_pocet - t7.vakciny_vydane_pocet,
                vakciny_ockovane_pocet_zmena_tyden = t0.vakciny_ockovane_pocet - t7.vakciny_ockovane_pocet,
                vakciny_znicene_pocet_zmena_tyden = t0.vakciny_znicene_pocet - t7.vakciny_znicene_pocet,
                vakciny_skladem_pocet_zmena_tyden = t0.vakciny_skladem_pocet - t7.vakciny_skladem_pocet
            from ockovaci_mista_metriky t0 
            join ockovaci_mista_metriky t7
            on t0.misto_id = t7.misto_id
            where t.misto_id = t0.misto_id and t.datum = :datum and t0.datum = :datum and t7.datum = :datum_7  
            """
        ), {'datum': self._date, 'datum_7': self._date - timedelta(7)})

        app.logger.info('Computing vaccination centers metrics - deltas finished.')

    def _compute_okres_population(self):
        """Computes metrics based on population for each okres."""
        population = db.session.query(
            Okres.id, func.sum(Populace.pocet).label('pocet_obyvatel_celkem'),
            func.sum(case([(Populace.vek >= 18, Populace.pocet)], else_=0)).label('pocet_obyvatel_dospeli')
        ).join(Populace, Populace.orp_kod == Okres.id) \
            .group_by(Okres.id)

        for pop in population:
            db.session.merge(OkresMetriky(
                okres_id=pop.id,
                datum=self._date,
                pocet_obyvatel_celkem=pop.pocet_obyvatel_celkem,
                pocet_obyvatel_dospeli=pop.pocet_obyvatel_dospeli
            ))

        app.logger.info('Computing okres metrics - population finished.')

    def _compute_okres_registrations(self):
        """Computes metrics based on registrations dataset for each okres."""
        registrations = db.session.query(
            Okres.id, func.sum(OckovaciMistoMetriky.registrace_celkem).label('registrace_celkem'),
            func.sum(OckovaciMistoMetriky.registrace_fronta).label("registrace_fronta")
        ).join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaciMistoMetriky, OckovaciMistoMetriky.misto_id == OckovaciMisto.id) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .group_by(Okres.id) \
            .all()

        for registration in registrations:
            db.session.merge(OkresMetriky(
                okres_id=registration.id,
                datum=self._date,
                registrace_celkem=registration.registrace_celkem,
                registrace_fronta=registration.registrace_fronta
            ))

        app.logger.info('Computing okres metrics - registrations finished.')

    def _compute_okres_reservations(self):
        """Computes metrics based on reservations dataset for each okres."""
        reservations = db.session.query(
            Okres.id, func.sum(OckovaciMistoMetriky.rezervace_celkem).label('rezervace_celkem'),
            func.sum(OckovaciMistoMetriky.rezervace_cekajici).label("rezervace_cekajici")
        ).join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaciMistoMetriky, OckovaciMistoMetriky.misto_id == OckovaciMisto.id) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .group_by(Okres.id) \
            .all()

        for reservation in reservations:
            db.session.merge(OkresMetriky(
                okres_id=reservation.id,
                datum=self._date,
                rezervace_celkem=reservation.rezervace_celkem,
                rezervace_cekajici=reservation.rezervace_cekajici
            ))

        app.logger.info('Computing okres metrics - reservations finished.')

    def _compute_okres_distributed(self):
        """Computes metrics based on distributed vaccines dataset for each okres."""
        distributed = db.session.query(
            Okres.id, func.sum(OckovaciMistoMetriky.vakciny_prijate_pocet).label('vakciny_prijate_pocet'),
            func.sum(OckovaciMistoMetriky.vakciny_vydane_pocet).label("vakciny_vydane_pocet")
        ).join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaciMistoMetriky, OckovaciMistoMetriky.misto_id == OckovaciMisto.id) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .group_by(Okres.id) \
            .all()

        for dist in distributed:
            db.session.merge(OkresMetriky(
                okres_id=dist.id,
                datum=self._date,
                vakciny_prijate_pocet=dist.vakciny_prijate_pocet,
                vakciny_vydane_pocet=dist.vakciny_vydane_pocet
            ))

        app.logger.info('Computing okres metrics - distributed vaccines finished.')

    def _compute_okres_used(self):
        """Computes metrics based on used vaccines dataset for each okres."""
        used = db.session.query(
            Okres.id, func.sum(OckovaciMistoMetriky.vakciny_ockovane_pocet).label('vakciny_ockovane_pocet'),
            func.sum(OckovaciMistoMetriky.vakciny_znicene_pocet).label("vakciny_znicene_pocet")
        ).join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaciMistoMetriky, OckovaciMistoMetriky.misto_id == OckovaciMisto.id) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .group_by(Okres.id) \
            .all()

        for use in used:
            db.session.merge(OkresMetriky(
                okres_id=use.id,
                datum=self._date,
                vakciny_ockovane_pocet=use.vakciny_ockovane_pocet,
                vakciny_znicene_pocet=use.vakciny_znicene_pocet
            ))

        app.logger.info('Computing okres metrics - used vaccines finished.')

    def _compute_okres_derived(self):
        """Computes metrics derived from the previous metrics for each okres."""
        avg_waiting = db.session.query(
            Okres.id,
            func.avg(OckovaniRegistrace.datum_rezervace - OckovaniRegistrace.datum).label('registrace_prumer_cekani'),
        ).join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum_rezervace >= self._date - timedelta(7)) \
            .group_by(Okres.id) \
            .all()

        for wait in avg_waiting:
            db.session.merge(OkresMetriky(
                okres_id=wait.id,
                datum=self._date,
                registrace_prumer_cekani=wait.registrace_prumer_cekani
            ))

        success_ratio_7 = db.session.query(
            Okres.id,
            (1.0 * func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == True, OckovaniRegistrace.pocet)], else_=0)), 0)
             / case([(func.sum(OckovaniRegistrace.pocet) == 0, None)], else_=func.sum(OckovaniRegistrace.pocet))).label('registrace_tydenni_uspesnost')
        ).join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum >= self._date - timedelta(7)) \
            .group_by(Okres.id) \
            .all()

        for ratio in success_ratio_7:
            db.session.merge(OkresMetriky(
                okres_id=ratio.id,
                datum=self._date,
                registrace_tydenni_uspesnost=ratio.registrace_tydenni_uspesnost
            ))

        success_ratio_14 = db.session.query(
            Okres.id,
            (1.0 * func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == True, OckovaniRegistrace.pocet)], else_=0)), 0)
             / case([(func.sum(OckovaniRegistrace.pocet) == 0, None)], else_=func.sum(OckovaniRegistrace.pocet))).label('registrace_14denni_uspesnost')
        ).join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum >= self._date - timedelta(14)) \
            .group_by(Okres.id) \
            .all()

        for ratio in success_ratio_14:
            db.session.merge(OkresMetriky(
                okres_id=ratio.id,
                datum=self._date,
                registrace_14denni_uspesnost=ratio.registrace_14denni_uspesnost
            ))

        success_ratio_30 = db.session.query(
            Okres.id,
            (1.0 * func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == True, OckovaniRegistrace.pocet)], else_=0)), 0)
             / case([(func.sum(OckovaniRegistrace.pocet) == 0, None)], else_=func.sum(OckovaniRegistrace.pocet))).label('registrace_30denni_uspesnost')
        ).join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum >= self._date - timedelta(30)) \
            .group_by(Okres.id) \
            .all()

        for ratio in success_ratio_30:
            db.session.merge(OkresMetriky(
                okres_id=ratio.id,
                datum=self._date,
                registrace_30denni_uspesnost=ratio.registrace_30denni_uspesnost
            ))

        app.logger.info('Computing okres metrics - derived metrics finished.')

    def _compute_okres_deltas(self):
        """Computes deltas for previous metrics for each okres."""
        db.session.execute(text(
            """
            update okresy_metriky t
            set rezervace_celkem_zmena_den = t0.rezervace_celkem - t1.rezervace_celkem,
                rezervace_cekajici_zmena_den = t0.rezervace_cekajici - t1.rezervace_cekajici,
                registrace_celkem_zmena_den = t0.registrace_celkem - t1.registrace_celkem,
                registrace_fronta_zmena_den = t0.registrace_fronta - t1.registrace_fronta,
                registrace_tydenni_uspesnost_zmena_den = t0.registrace_tydenni_uspesnost - t1.registrace_tydenni_uspesnost,
                registrace_14denni_uspesnost_zmena_den = t0.registrace_14denni_uspesnost - t1.registrace_14denni_uspesnost,
                registrace_30denni_uspesnost_zmena_den = t0.registrace_30denni_uspesnost - t1.registrace_30denni_uspesnost,
                registrace_prumer_cekani_zmena_den = t0.registrace_prumer_cekani - t1.registrace_prumer_cekani,
                vakciny_prijate_pocet_zmena_den = t0.vakciny_prijate_pocet - t1.vakciny_prijate_pocet,
                vakciny_vydane_pocet_zmena_den = t0.vakciny_vydane_pocet - t1.vakciny_vydane_pocet,
                vakciny_ockovane_pocet_zmena_den = t0.vakciny_ockovane_pocet - t1.vakciny_ockovane_pocet,
                vakciny_znicene_pocet_zmena_den = t0.vakciny_znicene_pocet - t1.vakciny_znicene_pocet
            from okresy_metriky t0 
            join okresy_metriky t1
            on t0.okres_id = t1.okres_id
            where t.okres_id = t0.okres_id and t.datum = :datum and t0.datum = :datum and t1.datum = :datum_1  
            """
        ), {'datum': self._date, 'datum_1': self._date - timedelta(1)})

        db.session.execute(text(
            """
            update okresy_metriky t
            set rezervace_celkem_zmena_tyden = t0.rezervace_celkem - t7.rezervace_celkem,
                rezervace_cekajici_zmena_tyden = t0.rezervace_cekajici - t7.rezervace_cekajici,
                registrace_celkem_zmena_tyden = t0.registrace_celkem - t7.registrace_celkem,
                registrace_fronta_zmena_tyden = t0.registrace_fronta - t7.registrace_fronta,
                registrace_tydenni_uspesnost_zmena_tyden = t0.registrace_tydenni_uspesnost - t7.registrace_tydenni_uspesnost,
                registrace_14denni_uspesnost_zmena_tyden = t0.registrace_14denni_uspesnost - t7.registrace_14denni_uspesnost,
                registrace_30denni_uspesnost_zmena_tyden = t0.registrace_30denni_uspesnost - t7.registrace_30denni_uspesnost,
                registrace_prumer_cekani_zmena_tyden = t0.registrace_prumer_cekani - t7.registrace_prumer_cekani,
                vakciny_prijate_pocet_zmena_tyden = t0.vakciny_prijate_pocet - t7.vakciny_prijate_pocet,
                vakciny_vydane_pocet_zmena_tyden = t0.vakciny_vydane_pocet - t7.vakciny_vydane_pocet,
                vakciny_ockovane_pocet_zmena_tyden = t0.vakciny_ockovane_pocet - t7.vakciny_ockovane_pocet,
                vakciny_znicene_pocet_zmena_tyden = t0.vakciny_znicene_pocet - t7.vakciny_znicene_pocet
            from okresy_metriky t0 
            join okresy_metriky t7
            on t0.okres_id = t7.okres_id
            where t.okres_id = t0.okres_id and t.datum = :datum and t0.datum = :datum and t7.datum = :datum_7  
            """
        ), {'datum': self._date, 'datum_7': self._date - timedelta(7)})

        app.logger.info('Computing okres metrics - deltas finished.')

    def _compute_kraj_population(self):
        """Computes metrics based on population for each okres."""
        population = db.session.query(
            Kraj.id, func.sum(Populace.pocet).label('pocet_obyvatel_celkem'),
            func.sum(case([(Populace.vek >= 18, Populace.pocet)], else_=0)).label('pocet_obyvatel_dospeli')
        ).join(Populace, Populace.orp_kod == Kraj.id) \
            .group_by(Kraj.id)

        for pop in population:
            db.session.merge(KrajMetriky(
                kraj_id=pop.id,
                datum=self._date,
                pocet_obyvatel_celkem=pop.pocet_obyvatel_celkem,
                pocet_obyvatel_dospeli=pop.pocet_obyvatel_dospeli
            ))

        app.logger.info('Computing kraj metrics - population finished.')

    def _compute_kraj_registrations(self):
        """Computes metrics based on registrations dataset for each kraj."""
        registrations = db.session.query(
            Kraj.id, func.sum(OckovaciMistoMetriky.registrace_celkem).label('registrace_celkem'),
            func.sum(OckovaciMistoMetriky.registrace_fronta).label("registrace_fronta")
        ).join(Okres, Okres.kraj_id == Kraj.id) \
            .join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaciMistoMetriky, OckovaciMistoMetriky.misto_id == OckovaciMisto.id) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .group_by(Kraj.id) \
            .all()

        for registration in registrations:
            db.session.merge(KrajMetriky(
                kraj_id=registration.id,
                datum=self._date,
                registrace_celkem=registration.registrace_celkem,
                registrace_fronta=registration.registrace_fronta
            ))

        app.logger.info('Computing kraj metrics - registrations finished.')

    def _compute_kraj_reservations(self):
        """Computes metrics based on reservations dataset for each kraj."""
        reservations = db.session.query(
            Kraj.id, func.sum(OckovaciMistoMetriky.rezervace_celkem).label('rezervace_celkem'),
            func.sum(OckovaciMistoMetriky.rezervace_cekajici).label("rezervace_cekajici")
        ).join(Okres, Okres.kraj_id == Kraj.id) \
            .join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaciMistoMetriky, OckovaciMistoMetriky.misto_id == OckovaciMisto.id) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .group_by(Kraj.id) \
            .all()

        for reservation in reservations:
            db.session.merge(KrajMetriky(
                kraj_id=reservation.id,
                datum=self._date,
                rezervace_celkem=reservation.rezervace_celkem,
                rezervace_cekajici=reservation.rezervace_cekajici
            ))

        app.logger.info('Computing kraj metrics - reservations finished.')

    def _compute_kraj_vaccinated(self):
        """Computes metrics based on vaccinated people dataset for each kraj."""
        vaccinated = db.session.query(
            Kraj.id, func.coalesce(func.sum(OckovaniLide.pocet), 0).label('ockovani_pocet'),
            func.coalesce(func.sum(case([(OckovaniLide.poradi_davky == 1, OckovaniLide.pocet)], else_=0)), 0).label('ockovani_pocet_1'),
            func.coalesce(func.sum(case([(OckovaniLide.poradi_davky == 2, OckovaniLide.pocet)], else_=0)), 0).label('ockovani_pocet_2')
        ).outerjoin(OckovaniLide, and_(OckovaniLide.kraj_nuts_kod == Kraj.id, OckovaniLide.datum < self._date)) \
            .group_by(Kraj.id) \
            .all()

        for vacc in vaccinated:
            db.session.merge(KrajMetriky(
                kraj_id=vacc.id,
                datum=self._date,
                ockovani_pocet=vacc.ockovani_pocet,
                ockovani_pocet_1=vacc.ockovani_pocet_1,
                ockovani_pocet_2=vacc.ockovani_pocet_2
            ))

        app.logger.info('Computing kraj metrics - vaccinated people finished.')

    def _compute_kraj_distributed(self):
        """Computes metrics based on distributed vaccines dataset for each kraj."""
        distributed = db.session.query(
            Kraj.id, func.sum(OckovaciMistoMetriky.vakciny_prijate_pocet).label('vakciny_prijate_pocet'),
            func.sum(OckovaciMistoMetriky.vakciny_vydane_pocet).label("vakciny_vydane_pocet")
        ).join(Okres, Okres.kraj_id == Kraj.id) \
            .join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaciMistoMetriky, OckovaciMistoMetriky.misto_id == OckovaciMisto.id) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .group_by(Kraj.id) \
            .all()

        for dist in distributed:
            db.session.merge(KrajMetriky(
                kraj_id=dist.id,
                datum=self._date,
                vakciny_prijate_pocet=dist.vakciny_prijate_pocet,
                vakciny_vydane_pocet=dist.vakciny_vydane_pocet
            ))

        app.logger.info('Computing kraj metrics - distributed vaccines finished.')

    def _compute_kraj_used(self):
        """Computes metrics based on used vaccines dataset for each kraj."""
        used = db.session.query(
            Kraj.id, func.sum(OckovaciMistoMetriky.vakciny_ockovane_pocet).label('vakciny_ockovane_pocet'),
            func.sum(OckovaciMistoMetriky.vakciny_znicene_pocet).label("vakciny_znicene_pocet")
        ).join(Okres, Okres.kraj_id == Kraj.id) \
            .join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaciMistoMetriky, OckovaciMistoMetriky.misto_id == OckovaciMisto.id) \
            .filter(OckovaciMistoMetriky.datum == self._date) \
            .group_by(Kraj.id) \
            .all()

        for use in used:
            db.session.merge(KrajMetriky(
                kraj_id=use.id,
                datum=self._date,
                vakciny_ockovane_pocet=use.vakciny_ockovane_pocet,
                vakciny_znicene_pocet=use.vakciny_znicene_pocet
            ))

        app.logger.info('Computing kraj metrics - used vaccines finished.')

    def _compute_kraj_derived(self):
        """Computes metrics derived from the previous metrics for each kraj."""
        avg_waiting = db.session.query(
            Kraj.id,
            func.avg(OckovaniRegistrace.datum_rezervace - OckovaniRegistrace.datum).label('registrace_prumer_cekani'),
        ).join(Okres, Okres.kraj_id == Kraj.id) \
            .join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum_rezervace >= self._date - timedelta(7)) \
            .group_by(Kraj.id) \
            .all()

        for wait in avg_waiting:
            db.session.merge(KrajMetriky(
                kraj_id=wait.id,
                datum=self._date,
                registrace_prumer_cekani=wait.registrace_prumer_cekani
            ))

        success_ratio_7 = db.session.query(
            Kraj.id,
            (1.0 * func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == True, OckovaniRegistrace.pocet)], else_=0)), 0)
             / case([(func.sum(OckovaniRegistrace.pocet) == 0, None)], else_=func.sum(OckovaniRegistrace.pocet))).label('registrace_tydenni_uspesnost')
        ).join(Okres, Okres.kraj_id == Kraj.id) \
            .join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum >= self._date - timedelta(7)) \
            .group_by(Kraj.id) \
            .all()

        for ratio in success_ratio_7:
            db.session.merge(KrajMetriky(
                kraj_id=ratio.id,
                datum=self._date,
                registrace_tydenni_uspesnost=ratio.registrace_tydenni_uspesnost
            ))

        success_ratio_14 = db.session.query(
            Kraj.id,
            (1.0 * func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == True, OckovaniRegistrace.pocet)], else_=0)), 0)
             / case([(func.sum(OckovaniRegistrace.pocet) == 0, None)], else_=func.sum(OckovaniRegistrace.pocet))).label('registrace_14denni_uspesnost')
        ).join(Okres, Okres.kraj_id == Kraj.id) \
            .join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum >= self._date - timedelta(14)) \
            .group_by(Kraj.id) \
            .all()

        for ratio in success_ratio_14:
            db.session.merge(KrajMetriky(
                kraj_id=ratio.id,
                datum=self._date,
                registrace_14denni_uspesnost=ratio.registrace_14denni_uspesnost
            ))

        success_ratio_30 = db.session.query(
            Kraj.id,
            (1.0 * func.coalesce(func.sum(case([(OckovaniRegistrace.rezervace == True, OckovaniRegistrace.pocet)], else_=0)), 0)
             / case([(func.sum(OckovaniRegistrace.pocet) == 0, None)], else_=func.sum(OckovaniRegistrace.pocet))).label('registrace_30denni_uspesnost')
        ).join(Okres, Okres.kraj_id == Kraj.id) \
            .join(OckovaciMisto, (OckovaciMisto.okres_id == Okres.id)) \
            .join(OckovaniRegistrace, OckovaciMisto.id == OckovaniRegistrace.ockovaci_misto_id) \
            .filter(OckovaniRegistrace.import_id == self._import_id) \
            .filter(OckovaniRegistrace.datum >= self._date - timedelta(30)) \
            .group_by(Kraj.id) \
            .all()

        for ratio in success_ratio_30:
            db.session.merge(KrajMetriky(
                kraj_id=ratio.id,
                datum=self._date,
                registrace_30denni_uspesnost=ratio.registrace_30denni_uspesnost
            ))

        vacc_skladem = db.session.query(
            Kraj.id, (KrajMetriky.vakciny_prijate_pocet - KrajMetriky.vakciny_vydane_pocet - KrajMetriky.ockovani_pocet
                      - KrajMetriky.vakciny_znicene_pocet).label('vakciny_skladem_pocet')
        ).join(KrajMetriky, Kraj.id == KrajMetriky.kraj_id) \
            .filter(KrajMetriky.datum == self._date) \
            .group_by(Kraj.id, KrajMetriky.vakciny_prijate_pocet, KrajMetriky.vakciny_vydane_pocet,
                      KrajMetriky.ockovani_pocet, KrajMetriky.vakciny_znicene_pocet) \
            .all()

        for vacc in vacc_skladem:
            db.session.merge(KrajMetriky(
                kraj_id=vacc.id,
                datum=self._date,
                vakciny_skladem_pocet=vacc.vakciny_skladem_pocet
            ))

        app.logger.info('Computing kraj metrics - derived metrics finished.')

    def _compute_kraj_deltas(self):
        """Computes deltas for previous metrics for each kraj."""
        db.session.execute(text(
            """
            update kraje_metriky t
            set rezervace_celkem_zmena_den = t0.rezervace_celkem - t1.rezervace_celkem,
                rezervace_cekajici_zmena_den = t0.rezervace_cekajici - t1.rezervace_cekajici,
                registrace_celkem_zmena_den = t0.registrace_celkem - t1.registrace_celkem,
                registrace_fronta_zmena_den = t0.registrace_fronta - t1.registrace_fronta,
                registrace_tydenni_uspesnost_zmena_den = t0.registrace_tydenni_uspesnost - t1.registrace_tydenni_uspesnost,
                registrace_14denni_uspesnost_zmena_den = t0.registrace_14denni_uspesnost - t1.registrace_14denni_uspesnost,
                registrace_30denni_uspesnost_zmena_den = t0.registrace_30denni_uspesnost - t1.registrace_30denni_uspesnost,
                registrace_prumer_cekani_zmena_den = t0.registrace_prumer_cekani - t1.registrace_prumer_cekani,
                ockovani_pocet_zmena_den = t0.ockovani_pocet - t1.ockovani_pocet,
                ockovani_pocet_1_zmena_den = t0.ockovani_pocet_1 - t1.ockovani_pocet_1,
                ockovani_pocet_2_zmena_den = t0.ockovani_pocet_2 - t1.ockovani_pocet_2,
                vakciny_prijate_pocet_zmena_den = t0.vakciny_prijate_pocet - t1.vakciny_prijate_pocet,
                vakciny_vydane_pocet_zmena_den = t0.vakciny_vydane_pocet - t1.vakciny_vydane_pocet,
                vakciny_ockovane_pocet_zmena_den = t0.vakciny_ockovane_pocet - t1.vakciny_ockovane_pocet,
                vakciny_znicene_pocet_zmena_den = t0.vakciny_znicene_pocet - t1.vakciny_znicene_pocet,
                vakciny_skladem_pocet_zmena_den = t0.vakciny_skladem_pocet - t1.vakciny_skladem_pocet
            from kraje_metriky t0 
            join kraje_metriky t1
            on t0.kraj_id = t1.kraj_id
            where t.kraj_id = t0.kraj_id and t.datum = :datum and t0.datum = :datum and t1.datum = :datum_1  
            """
        ), {'datum': self._date, 'datum_1': self._date - timedelta(1)})

        db.session.execute(text(
            """
            update kraje_metriky t
            set rezervace_celkem_zmena_tyden = t0.rezervace_celkem - t7.rezervace_celkem,
                rezervace_cekajici_zmena_tyden = t0.rezervace_cekajici - t7.rezervace_cekajici,
                registrace_celkem_zmena_tyden = t0.registrace_celkem - t7.registrace_celkem,
                registrace_fronta_zmena_tyden = t0.registrace_fronta - t7.registrace_fronta,
                registrace_tydenni_uspesnost_zmena_tyden = t0.registrace_tydenni_uspesnost - t7.registrace_tydenni_uspesnost,
                registrace_14denni_uspesnost_zmena_tyden = t0.registrace_14denni_uspesnost - t7.registrace_14denni_uspesnost,
                registrace_30denni_uspesnost_zmena_tyden = t0.registrace_30denni_uspesnost - t7.registrace_30denni_uspesnost,
                registrace_prumer_cekani_zmena_tyden = t0.registrace_prumer_cekani - t7.registrace_prumer_cekani,
                ockovani_pocet_zmena_tyden = t0.ockovani_pocet - t7.ockovani_pocet,
                ockovani_pocet_1_zmena_tyden = t0.ockovani_pocet_1 - t7.ockovani_pocet_1,
                ockovani_pocet_2_zmena_tyden = t0.ockovani_pocet_2 - t7.ockovani_pocet_2,
                vakciny_prijate_pocet_zmena_tyden = t0.vakciny_prijate_pocet - t7.vakciny_prijate_pocet,
                vakciny_vydane_pocet_zmena_tyden = t0.vakciny_vydane_pocet - t7.vakciny_vydane_pocet,
                vakciny_ockovane_pocet_zmena_tyden = t0.vakciny_ockovane_pocet - t7.vakciny_ockovane_pocet,
                vakciny_znicene_pocet_zmena_tyden = t0.vakciny_znicene_pocet - t7.vakciny_znicene_pocet,
                vakciny_skladem_pocet_zmena_tyden = t0.vakciny_skladem_pocet - t7.vakciny_skladem_pocet
            from kraje_metriky t0 
            join kraje_metriky t7
            on t0.kraj_id = t7.kraj_id
            where t.kraj_id = t0.kraj_id and t.datum = :datum and t0.datum = :datum and t7.datum = :datum_7  
            """
        ), {'datum': self._date, 'datum_7': self._date - timedelta(7)})

        app.logger.info('Computing kraj metrics - deltas finished.')

    def _find_import_id(self):
        id_ = db.session.query(Import.id) \
            .filter(Import.date == self._date, Import.status == queries.STATUS_FINISHED) \
            .first()

        if id_ is None:
            raise Exception("No data for date: '{0}'.".format(self._date))

        return id_[0]


if __name__ == '__main__':
    etl = Etl(date.today())
    etl.compute_all()