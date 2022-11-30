APP=${1:-migas-staging}

echo $APP

ROOT=$(dirname $(dirname $(realpath $0)))

pushd $ROOT
# clear old builds
rm -rf build/
# rebuild app
python -m build
# push built app to heroku
heroku builds:create -a $APP --source-tar=dist/$(python setup.py --fullname).tar.gz
popd
