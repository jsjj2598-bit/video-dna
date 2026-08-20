import os
import tempfile

_test_data = tempfile.TemporaryDirectory(prefix="video-dna-tests-")
os.environ["VIDEODNA_DATA_DIR"] = _test_data.name

