wget -r http://127.0.0.1:5001/ockovani-covid/
find ./127.0.0.1:5001/ -type f -print0 | xargs -0 -I{} mv "{}" "{}".html
mv ./127.0.0.1:5001/ockovani-covid/index.html.html ./127.0.0.1:5001/ockovani-covid/index.html

cp -r 127.0.0.1:5001/* /home/ockovani/web/msusicky.github.io/
rm -r 127.0.0.1:5001
cd /home/ockovani/web/msusicky.github.io/ockovani-covid
git add *
git commit -m "Update"
git push origin master

