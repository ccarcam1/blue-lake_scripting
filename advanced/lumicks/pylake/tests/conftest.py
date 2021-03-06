import h5py
import numpy as np
import pytest
import json


# We generate mock data files for different versions of the Bluelake HDF5 file
# format:

class MockDataFile_v1:

    def __init__(self, file):
        self.file = h5py.File(file, 'w')

    def get_file_format_version(self):
        return 1

    def write_metadata(self):
        self.file.attrs["Bluelake version"] = "unknown"
        self.file.attrs["File format version"] = self.get_file_format_version()
        self.file.attrs["Experiment"] = ""
        self.file.attrs["Description"] = ""
        self.file.attrs["GUID"] = ""
        self.file.attrs["Export time (ns)"] = -1

    def make_continuous_channel(self, group, name, start, dt, data):
        if group not in self.file:
            self.file.create_group(group)

        self.file[group][name] = data
        dset = self.file[group][name]
        dset.attrs["Start time (ns)"] = start
        dset.attrs["Stop time (ns)"] = start + len(data) * dt
        dset.attrs["Sample rate (Hz)"] = 1 / dt * 1e9
        return dset

    def make_timeseries_channel(self, group, name, data):
        if group not in self.file:
            self.file.create_group(group)

        compound_type = np.dtype([("Timestamp", np.int64), ("Value", float)])
        self.file[group][name] = np.array(data, compound_type)
        dset = self.file[group][name]
        return dset

    def make_timetags_channel(self, group, name, data):
        raise NotImplementedError


class MockDataFile_v2(MockDataFile_v1):

    def get_file_format_version(self):
        return 2

    def make_calibration_data(self, calibration_idx, group, attributes):
        if "Calibration" not in self.file:
            self.file.create_group("Calibration")

        # Numeric value converted to string
        if calibration_idx not in self.file["Calibration"]:
            self.file["Calibration"].create_group(calibration_idx)

        # e.g. Force 1x, Force 1y ... etc
        if group not in self.file["Calibration"][calibration_idx]:
            self.file["Calibration"][calibration_idx].create_group(group)

        # Attributes
        field = self.file["Calibration"][calibration_idx][group]
        for i, v in attributes.items():
            field.attrs[i] = v

    def make_continuous_channel(self, group, name, start, dt, data):
        dset = super().make_continuous_channel(group, name, start, dt, data)
        dset.attrs["Kind"] = "Continuous"

    def make_timeseries_channel(self, group, name, data):
        dset = super().make_timeseries_channel(group, name, data)
        dset.attrs["Kind"] = b"TimeSeries"

    def make_json_data(self, group, name, data):
        if group not in self.file:
            self.file.create_group(group)

        data_location = group + "_" + name
        self.file.create_group(data_location)

        self.file[group][name] = self.file[data_location].create_dataset("value0", data=data)
        return self.file[group][name]

    def make_timetags_channel(self, group, name, data):
        if group not in self.file:
            self.file.create_group(group)

        self.file[group][name] = data
        dset = self.file[group][name]
        dset.attrs["Kind"] = "TimeTags"
        return dset


@pytest.fixture(scope="session", params=[MockDataFile_v1, MockDataFile_v2])
def h5_file(tmpdir_factory, request):
    mock_class = request.param

    tmpdir = tmpdir_factory.mktemp("pylake")
    mock_file = mock_class(tmpdir.join("%s.h5" % mock_class.__class__.__name__))
    mock_file.write_metadata()

    mock_file.make_continuous_channel("Force HF", "Force 1x", 1, 10, np.arange(5.0))
    mock_file.make_continuous_channel("Force HF", "Force 1y", 1, 10, np.arange(5.0, 10.0))

    mock_file.make_timeseries_channel("Force LF", "Force 1x", [(1, 1.1), (2, 2.1)])
    mock_file.make_timeseries_channel("Force LF", "Force 1y", [(1, 1.2), (2, 2.2)])

    if mock_class == MockDataFile_v2:
        mock_file.make_timetags_channel(
            "Photon Time Tags", "Red",
            np.arange(10, 100, step=10, dtype=np.int64))

        calibration_time_field = "Stop time (ns)"
        mock_file.make_calibration_data("1", "Force 1x", {calibration_time_field: 0})
        mock_file.make_calibration_data("2", "Force 1x", {calibration_time_field: 1})
        mock_file.make_calibration_data("3", "Force 1x", {calibration_time_field: 10})
        mock_file.make_calibration_data("4", "Force 1x", {calibration_time_field: 100})
        mock_file.make_calibration_data("1", "Force 1y", {calibration_time_field: 0})
        mock_file.make_calibration_data("2", "Force 1y", {calibration_time_field: 1})
        mock_file.make_calibration_data("3", "Force 1y", {calibration_time_field: 10})
        mock_file.make_calibration_data("4", "Force 1y", {calibration_time_field: 100})

        counts = [2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 1, 8, 0,
                  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 0,
                  1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 8, 0,
                  0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 8, 0]

        infowave = [1, 0, 2, 1, 0, 2, 1, 0, 2, 1, 0, 2, 1, 0, 0, 2,
                    0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 0, 2,
                    1, 0, 2, 1, 0, 2, 1, 0, 2, 1, 0, 2, 1, 0, 0, 2,
                    0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 0, 2]

        enc = json.JSONEncoder()

        json_string = enc.encode({
            "value0": {
                "cereal_class_version": 1,
                "fluorescence": True,
                "force": False,
                "scan count": 0,
                "scan volume": {
                    "center point (um)": {
                        "x": 58.075877109272604,
                        "y": 31.978375270573267,
                        "z": 0
                    },
                    "cereal_class_version": 1,
                    "pixel time (ms)": 0.2,
                    "scan axes": [
                        {
                            "axis": 0,
                            "cereal_class_version": 1,
                            "num of pixels": 5,
                            "pixel size (nm)": 10,
                            "scan time (ms)": 0,
                            "scan width (um)": 36.07468112612217
                        }
                    ]
                }
            }
        })

        # Generate lines at 1 Hz
        freq = int(1e9 / 16)
        mock_file.make_continuous_channel("Photon count", "Red", int(20e9), freq, counts)
        mock_file.make_continuous_channel("Photon count", "Green", int(20e9), freq, counts)
        mock_file.make_continuous_channel("Photon count", "Blue", int(20e9), freq, counts)
        mock_file.make_continuous_channel("Info wave", "Info wave", int(20e9), freq, infowave)
        ds = mock_file.make_json_data("Kymograph", "Kymo1", json_string)
        ds.attrs["Start time (ns)"] = int(20e9)
        ds.attrs["Stop time (ns)"] = int(20e9 + len(infowave) * freq)

        json_string = enc.encode({
            "value0": {
                "cereal_class_version": 1,
                "fluorescence": True,
                "force": False,
                "scan count": 0,
                "scan volume": {
                    "center point (um)": {
                        "x": 58.075877109272604,
                        "y": 31.978375270573267,
                        "z": 0
                    },
                    "cereal_class_version": 1,
                    "pixel time (ms)": 0.2,
                    "scan axes": [
                        {
                            "axis": 1,
                            "cereal_class_version": 1,
                            "num of pixels": 4,
                            "pixel size (nm)": 10,
                            "scan time (ms)": 0,
                            "scan width (um)": 36.07468112612217
                        },
                        {
                            "axis": 0,
                            "cereal_class_version": 1,
                            "num of pixels": 5,
                            "pixel size (nm)": 10,
                            "scan time (ms)": 0,
                            "scan width (um)": 36.07468112612217
                        }
                    ]
                }
            }
        })

        ds = mock_file.make_json_data("Scan", "Scan1", json_string)
        ds.attrs["Start time (ns)"] = int(20e9)
        ds.attrs["Stop time (ns)"] = int(20e9 + len(infowave) * freq)

    return mock_file.file


@pytest.fixture(scope="session")
def h5_file_invalid_version(tmpdir_factory):
    tmpdir = tmpdir_factory.mktemp("pylake")

    mock_file = h5py.File(tmpdir.join("invalid.h5"), 'w')
    mock_file.attrs["Bluelake version"] = "unknown"
    mock_file.attrs["File format version"] = 254

    return mock_file

