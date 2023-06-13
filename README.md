# rshelperscripts
Helper Scripts for RayStation

TODO: Document everything...

# points
Poorly thought out and implemented 3d point for helper functions.  Also includes some rudimentarty FWHM searching.  Primarily useful in leiu of importing full numpy (which would require an enviroment change).  Otherwise, everything would be better by just using numpy.

# rsdicomread
Method to read in non-image dicom data from the ImageStack.DicomDataSet bytestream.  Also includes a subclass/wrapper to GzipFile objects to allow unpacking of arbitrary pack data.  Defeats the entire advantage of [points] library as this builds off pydicom which requires numpy...

# couchtop
Classes for couchtop information.  This builds from the couche models in our clinic which are implemeneted using the Structure Templates in RS.  This can be used to add a couch to an open plan and implements some logic (specific to our clinic, but reasonably extensible) to attempt to figure out exactly where the couch top should go.  It can also attempt to find the location of the H&N board and position the couch top appropriately for this.  This relies on both points and (if available) rsdicomread to pull in an absolute couch position (if that fails, it tries to guesss based on the site).


# Disclaimer
Anything from this repository is only for educational purposes and is not intended nor released for clinical use.
