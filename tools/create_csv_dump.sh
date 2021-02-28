psql -d ockovani -t -A -F"," -c "COPY (select k.misto_id, k.datum, k.data, k.volna_mista, ok.nazev as okres, kr.nazev as kraj, o.service_id, o.operation_id from volna_mista_den k join ockovaci_mista o on (k.misto_id=o.id) join okresy ok on (ok.id=o.okres_id) join kraje kr on (kr.id=ok.kraj_id) where k.import_id=(select max(id) from importy where status='FINISHED' and k.volna_mista>0)  ) TO STDOUT WITH CSV DELIMITER ',' HEADER QUOTE '\"' ESCAPE '\'" > /home/ockovani/web/msusicky.github.io/ockovani-covid/dump_kapacity.csv
psql -d ockovani -t -A -F"," -c "COPY (select k.misto_id, k.datum, k.volna_mista, o.nazev, ok.nazev as okres, kr.nazev as kraj, o.service_id, o.operation_id from volna_mista_den k join ockovaci_mista o on (k.misto_id=o.id) join okresy ok on (ok.id=o.okres_id) join kraje kr on (kr.id=ok.kraj_id)	where k.import_id=(select max(id) from importy where status='FINISHED' and k.volna_mista>0) ) TO STDOUT WITH CSV DELIMITER ',' HEADER QUOTE '\"' ESCAPE '\'" > /home/ockovani/web/msusicky.github.io/ockovani-covid/dump_kapacity_csv.csv