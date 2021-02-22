psql -d ockovani -t -A -F"," -c "COPY (select k.misto_id, k.datum, k.raw_data, k.pocet_mist, o.place_id, o.mesto, o.kraj, o.service_id, o.operation_id, o.covtest_id from kapacita k join ockovaci_misto o on (k.misto_id=o.misto_id) where k.import_id=(select max(import_id) from import_log where status='FINISHED' and k.pocet_mist>0) ) TO STDOUT WITH CSV DELIMITER ',' HEADER QUOTE '\"' ESCAPE '\'" > /home/ockovani/web/msusicky.github.io/ockovani-covid/dump_kapacity.csv