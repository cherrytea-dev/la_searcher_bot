import sys
import os

from pylint import lint

THRESHOLD = 9

FILE_NAME = os.getenv('FILE_NAME')
# example: check_first_posts_for_changes

run = lint.Run([f'{FILE_NAME}/main.py'], do_exit=False)

score = str(round(run.linter.stats.global_note, 2))

# save the Env Var
os.environ['LINT_SCORE'] = score

if score == THRESHOLD:

    print("Linter failed: Score < threshold value")

    # exit with error
    sys.exit(1)

# exit without any errors
sys.exit(0)
