# usage: sh tests/tools/make_archive.sh <function_folder>


FUNC_FOLDER=$1
  
echo "Creating archive for $FUNC_NAME"

uv export --extra $FUNC_FOLDER --no-hashes --no-dev > src/$FUNC_FOLDER/requirements.txt
ORIG_DIR=$(pwd)
ARCHIVE_NAME="$FUNC_FOLDER.zip"
cd src/ && \
zip -r "$ARCHIVE_NAME" \
    $FUNC_FOLDER \
    _dependencies \
    -x "*.pyc" -x "*__pycache__*"

zip -j "$ARCHIVE_NAME" \
    $FUNC_FOLDER/requirements.txt
    # add corresponding requirements to root of archive

cd "$ORIG_DIR"

echo "Archive $ARCHIVE_NAME created!"
