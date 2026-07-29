import h5py
import sys
import shutil


input_file = sys.argv[1]
output_file = sys.argv[2]


print("Copying:")
print(input_file)


# Copy file byte-for-byte first
shutil.copy(input_file, output_file)


print("Adding nfpc metadata")


with h5py.File(output_file, "r+") as f:

    # root attribute
    f.attrs["nfpc"] = 1024


    # data attribute
    if "data" in f:

        f["data"].attrs["nfpc"] = 1024


print("Saved:")
print(output_file)