#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
#--------------------------------------------------------------------------

import math
import os
import tempfile

import gdcm
import numpy
import vtk
import vtkgdcm
from wx.lib.pubsub import pub as Publisher

from scipy.ndimage import shift
from vtk.util import numpy_support

import constants as const
from data import vtk_utils
import utils

# TODO: Test cases which are originally in sagittal/coronal orientation
# and have gantry

def ResampleImage3D(imagedata, value):
    """
    Resample vtkImageData matrix.
    """
    spacing = imagedata.GetSpacing()
    extent = imagedata.GetExtent()
    size = imagedata.GetDimensions()

    width = float(size[0])
    height = float(size[1]/value)

    resolution = (height/(extent[1]-extent[0])+1)*spacing[1]

    resample = vtk.vtkImageResample()
    resample.SetInput(imagedata)
    resample.SetAxisMagnificationFactor(0, resolution)
    resample.SetAxisMagnificationFactor(1, resolution)

    return resample.GetOutput()

def ResampleImage2D(imagedata, px=None, py=None, resolution_percentage = None,
                        update_progress = None):
    """
    Resample vtkImageData matrix.
    """

    extent = imagedata.GetExtent()
    spacing = imagedata.GetSpacing()
    dimensions = imagedata.GetDimensions()

    if resolution_percentage:
        px = math.ceil(dimensions[0] * resolution_percentage)
        py = math.ceil(dimensions[1] * resolution_percentage)

    if abs(extent[1]-extent[3]) < abs(extent[3]-extent[5]):
        f = extent[1]
    elif abs(extent[1]-extent[5]) < abs(extent[1] - extent[3]):
        f = extent[1]
    elif abs(extent[3]-extent[5]) < abs(extent[1] - extent[3]):
        f = extent[3]
    else:
        f = extent[1]

    factor_x = px/float(f+1)
    factor_y = py/float(f+1)

    resample = vtk.vtkImageResample()
    resample.SetInput(imagedata)
    resample.SetAxisMagnificationFactor(0, factor_x)
    resample.SetAxisMagnificationFactor(1, factor_y)
    resample.SetOutputSpacing(spacing[0] * factor_x, spacing[1] * factor_y, spacing[2])
    if (update_progress):
        message = _("Generating multiplanar visualization...")
        resample.AddObserver("ProgressEvent", lambda obj,
                             evt:update_progress(resample,message))
    resample.Update()


    return resample.GetOutput()

def FixGantryTilt(matrix, spacing, tilt):
    """
    Fix gantry tilt given a vtkImageData and the tilt value. Return new
    vtkImageData.
    """
    angle = numpy.radians(tilt)
    spacing = spacing[0], spacing[1], spacing[2]
    gntan = math.tan(angle)

    for n, slice_ in enumerate(matrix):
        offset = gntan * n * spacing[2]
        matrix[n] = shift(slice_, (-offset/spacing[1], 0), cval=matrix.min())


def BuildEditedImage(imagedata, points):
    """
    Editing the original image in accordance with the edit
    points in the editor, it is necessary to generate the
    vtkPolyData via vtkContourFilter
    """
    init_values = None
    for point in points:
        x, y, z = point
        colour = points[point]
        imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)
        imagedata.Update()

        if not(init_values):
                xi = x
                xf = x
                yi = y
                yf = y
                zi = z
                zf = z
                init_values = 1

        if (xi > x):
            xi = x
        elif(xf < x):
            xf = x

        if (yi > y):
            yi = y
        elif(yf < y):
            yf = y

        if (zi > z):
            zi = z
        elif(zf < z):
            zf = z

    clip = vtk.vtkImageClip()
    clip.SetInput(imagedata)
    clip.SetOutputWholeExtent(xi, xf, yi, yf, zi, zf)
    clip.Update()

    gauss = vtk.vtkImageGaussianSmooth()
    gauss.SetInput(clip.GetOutput())
    gauss.SetRadiusFactor(0.6)
    gauss.Update()

    app = vtk.vtkImageAppend()
    app.PreserveExtentsOn()
    app.SetAppendAxis(2)
    app.SetInput(0, imagedata)
    app.SetInput(1, gauss.GetOutput())
    app.Update()

    return app.GetOutput()


def Export(imagedata, filename, bin=False):
    writer = vtk.vtkXMLImageDataWriter()
    writer.SetFileName(filename)
    if bin:
        writer.SetDataModeToBinary()
    else:
        writer.SetDataModeToAscii()
    #writer.SetInput(imagedata)
    #writer.Write()

def Import(filename):
    reader = vtk.vtkXMLImageDataReader()
    reader.SetFileName(filename)
    # TODO: Check if the code bellow is necessary
    reader.WholeSlicesOn()
    reader.Update()

    return reader.GetOutput()

def View(imagedata):
    viewer = vtk.vtkImageViewer()
    viewer.SetInput(imagedata)
    viewer.SetColorWindow(200)
    viewer.SetColorLevel(100)
    viewer.Render()

    import time
    time.sleep(10)

def ViewGDCM(imagedata):
    viewer = vtkgdcm.vtkImageColorViewer()
    viewer.SetInput(reader.GetOutput())
    viewer.SetColorWindow(500.)
    viewer.SetColorLevel(50.)
    viewer.Render()

    import time
    time.sleep(5)



def ExtractVOI(imagedata,xi,xf,yi,yf,zi,zf):
    """
    Cropping the vtkImagedata according
    with values.
    """
    voi = vtk.vtkExtractVOI()
    voi.SetVOI(xi,xf,yi,yf,zi,zf)
    voi.SetInput(imagedata)
    voi.SetSampleRate(1, 1, 1)
    voi.Update()
    return voi.GetOutput()

def CreateImageData(filelist, zspacing, xyspacing,size,
                                bits, use_dcmspacing):
    message = _("Generating multiplanar visualization...")

    if not const.VTK_WARNING:
        log_path = os.path.join(const.LOG_FOLDER, 'vtkoutput.txt')
        fow = vtk.vtkFileOutputWindow()
        fow.SetFileName(log_path)
        ow = vtk.vtkOutputWindow()
        ow.SetInstance(fow)

    x,y = size
    px, py = utils.predict_memory(len(filelist), x, y, bits)

    utils.debug("Image Resized to >>> %f x %f" % (px, py))

    if (x == px) and (y == py):
        const.REDUCE_IMAGEDATA_QUALITY = 0
    else:
        const.REDUCE_IMAGEDATA_QUALITY = 1

    if not(const.REDUCE_IMAGEDATA_QUALITY):
        update_progress= vtk_utils.ShowProgress(1, dialog_type = "ProgressDialog")

        array = vtk.vtkStringArray()
        for x in xrange(len(filelist)):
            array.InsertValue(x,filelist[x])

        reader = vtkgdcm.vtkGDCMImageReader()
        reader.SetFileNames(array)
        reader.AddObserver("ProgressEvent", lambda obj,evt:
                     update_progress(reader,message))
        reader.Update()

        # The zpacing is a DicomGroup property, so we need to set it
        imagedata = vtk.vtkImageData()
        imagedata.DeepCopy(reader.GetOutput())
        if (use_dcmspacing):
            spacing = xyspacing
            spacing[2] = zspacing
        else:
            spacing = imagedata.GetSpacing()

        imagedata.SetSpacing(spacing[0], spacing[1], zspacing)
    else:

        update_progress= vtk_utils.ShowProgress(2*len(filelist),
                                            dialog_type = "ProgressDialog")

        # Reformat each slice and future append them
        appender = vtk.vtkImageAppend()
        appender.SetAppendAxis(2) #Define Stack in Z


        # Reformat each slice
        for x in xrange(len(filelist)):
            # TODO: We need to check this automatically according
            # to each computer's architecture
            # If the resolution of the matrix is too large
            reader = vtkgdcm.vtkGDCMImageReader()
            reader.SetFileName(filelist[x])
            reader.AddObserver("ProgressEvent", lambda obj,evt:
                         update_progress(reader,message))
            reader.Update()

            if (use_dcmspacing):
                spacing = xyspacing
                spacing[2] = zspacing
            else:
                spacing = reader.GetOutput().GetSpacing()

            tmp_image = vtk.vtkImageData()
            tmp_image.DeepCopy(reader.GetOutput())
            tmp_image.SetSpacing(spacing[0], spacing[1], zspacing)
            tmp_image.Update()

            #Resample image in x,y dimension
            slice_imagedata = ResampleImage2D(tmp_image, px, py, update_progress)
            #Stack images in Z axes
            appender.AddInput(slice_imagedata)
            #appender.AddObserver("ProgressEvent", lambda obj,evt:update_progress(appender))
            appender.Update()

        spacing = appender.GetOutput().GetSpacing()

        # The zpacing is a DicomGroup property, so we need to set it
        imagedata = vtk.vtkImageData()
        imagedata.DeepCopy(appender.GetOutput())
        imagedata.SetSpacing(spacing[0], spacing[1], zspacing)

    imagedata.AddObserver("ProgressEvent", lambda obj,evt:
                 update_progress(imagedata,message))
    imagedata.Update()

    return imagedata


class ImageCreator:
    def __init__(self):
        self.running = True
        Publisher.subscribe(self.CancelImageDataLoad, "Cancel DICOM load")

    def CancelImageDataLoad(self, evt_pusub):
        utils.debug("Canceling")
        self.running = False

    def CreateImageData(self, filelist, zspacing, size, bits):
        message = _("Generating multiplanar visualization...")

        if not const.VTK_WARNING:
            log_path = os.path.join(const.LOG_FOLDER, 'vtkoutput.txt')
            fow = vtk.vtkFileOutputWindow()
            fow.SetFileName(log_path)
            ow = vtk.vtkOutputWindow()
            ow.SetInstance(fow)

        x,y = size
        px, py = utils.predict_memory(len(filelist), x, y, bits)
        utils.debug("Image Resized to >>> %f x %f" % (px, py))

        if (x == px) and (y == py):
            const.REDUCE_IMAGEDATA_QUALITY = 0
        else:
            const.REDUCE_IMAGEDATA_QUALITY = 1

        if not(const.REDUCE_IMAGEDATA_QUALITY):
            update_progress= vtk_utils.ShowProgress(1, dialog_type = "ProgressDialog")

            array = vtk.vtkStringArray()
            for x in xrange(len(filelist)):
                if not self.running:
                    return False
                array.InsertValue(x,filelist[x])

            if not self.running:
                return False
            reader = vtkgdcm.vtkGDCMImageReader()
            reader.SetFileNames(array)
            reader.AddObserver("ProgressEvent", lambda obj,evt:
                         update_progress(reader,message))
            reader.Update()

            if not self.running:
                reader.AbortExecuteOn()
                return False
            # The zpacing is a DicomGroup property, so we need to set it
            imagedata = vtk.vtkImageData()
            imagedata.DeepCopy(reader.GetOutput())
            spacing = imagedata.GetSpacing()
            imagedata.SetSpacing(spacing[0], spacing[1], zspacing)
        else:

            update_progress= vtk_utils.ShowProgress(2*len(filelist),
                                                dialog_type = "ProgressDialog")

            # Reformat each slice and future append them
            appender = vtk.vtkImageAppend()
            appender.SetAppendAxis(2) #Define Stack in Z


            # Reformat each slice
            for x in xrange(len(filelist)):
                # TODO: We need to check this automatically according
                # to each computer's architecture
                # If the resolution of the matrix is too large
                if not self.running:
                    return False
                reader = vtkgdcm.vtkGDCMImageReader()
                reader.SetFileName(filelist[x])
                reader.AddObserver("ProgressEvent", lambda obj,evt:
                             update_progress(reader,message))
                reader.Update()

                #Resample image in x,y dimension
                slice_imagedata = ResampleImage2D(reader.GetOutput(), px, py, update_progress)
                #Stack images in Z axes
                appender.AddInput(slice_imagedata)
                #appender.AddObserver("ProgressEvent", lambda obj,evt:update_progress(appender))
                appender.Update()

            # The zpacing is a DicomGroup property, so we need to set it
            if not self.running:
                return False
            imagedata = vtk.vtkImageData()
            imagedata.DeepCopy(appender.GetOutput())
            spacing = imagedata.GetSpacing()

            imagedata.SetSpacing(spacing[0], spacing[1], zspacing)

        imagedata.AddObserver("ProgressEvent", lambda obj,evt:
                     update_progress(imagedata,message))
        imagedata.Update()

        return imagedata


def get_stacking_direction(files, orientation):
    """
    Returns the direction of stacking in the given orientation:

    AXIAL:

    CORONAL:

    SAGITAL: +1 - Right -> Left
             -1 - Left  -> Right
    """
    r1 = vtkgdcm.vtkGDCMImageReader()
    r1.SetFileName(files[0])
    r1.Update()
    p1 = r1.GetImagePositionPatient()

    r2 = vtkgdcm.vtkGDCMImageReader()
    r2.SetFileName(files[1])
    r2.Update()
    p2 = r2.GetImagePositionPatient()

    dc = r1.GetMedicalImageProperties().GetDirectionCosine()
    dc1 = numpy.array(dc[:3])
    dc2 = numpy.array(dc[3:])
    dc3 = numpy.cross(dc1, dc2)

    distp = numpy.array(p2) - numpy.array(p1)
    ndistp = distp / numpy.linalg.norm(distp)
    distv = numpy.dot(dc3, ndistp)

    if orientation == 'SAGITTAL':
        
        if dc3[0] < 0:
            if distv > 0:
                dirx = -1
            else:
                dirx = 1
        else:
            if distv < 0:
                dirx = -1
            else:
                dirx = 1

        ds = [-1 if dc2[2] < 0 else 1,
              -1 if dc1[1] < 0 else 1,
              dirx,
             ]

    elif orientation == 'CORONAL':
        d = (p2[1] - p1[1])
        d = int(d / abs(d))
        ds = []

    else:
        print p1, p2
        d = (p2[2] - p1[2])
        d = int(d / abs(d))
        ds = []

    print "==================================="
    print dc1, dc2, dc3, ds, p2, p1, p2, distv
    print "==================================="

    return ds


def dcm2memmap(files, slice_size, orientation, resolution_percentage):
    """
    From a list of dicom files it creates memmap file in the temp folder and
    returns it and its related filename. The voxels are stored in the matrix in
    the RPI order (R-L within P-A within I-S , see
    http://www.grahamwideman.com/gw/brain/orientation/orientterms.htm), know as
    Radiological order. 
    """
    message = _("Generating multiplanar visualization...")
    update_progress= vtk_utils.ShowProgress(len(files) - 1, dialog_type = "ProgressDialog")

    temp_file = tempfile.mktemp()

    if orientation == 'SAGITTAL':
        if resolution_percentage == 1.0:
            shape = slice_size[0], slice_size[1], len(files)
        else:
            shape = math.ceil(slice_size[0]*resolution_percentage),\
                    math.ceil(slice_size[1]*resolution_percentage), len(files)

    elif orientation == 'CORONAL':
        if resolution_percentage == 1.0:
            shape = slice_size[1], len(files), slice_size[0]
        else:
            shape = math.ceil(slice_size[1]*resolution_percentage), len(files),\
                                        math.ceil(slice_size[0]*resolution_percentage)
    else:
        if resolution_percentage == 1.0:
            shape = len(files), slice_size[1], slice_size[0]
        else:
            shape = len(files), math.ceil(slice_size[1]*resolution_percentage),\
                                        math.ceil(slice_size[0]*resolution_percentage)

    matrix = numpy.memmap(temp_file, mode='w+', dtype='int16', shape=shape)

    # 1)  VTK doesn't follow the convention that the first pixel in a image is the
    #     top-left one. The first pixel pixel in VTK is the bottom-left one.
    dcm_reader = vtkgdcm.vtkGDCMImageReader()

    cont = 0
    max_scalar = None
    min_scalar = None

    d = get_stacking_direction(files, orientation)

    for n, f in enumerate(files):
        dcm_reader.SetFileName(f)
        dcm_reader.Update()
        image = dcm_reader.GetOutput()

        if resolution_percentage != 1.0:
            image_resized = ResampleImage2D(image, px=None, py=None,\
                                resolution_percentage = resolution_percentage, update_progress = None)

            image = image_resized
            print ">>>>>>>>>", image.GetDimensions()

        min_aux, max_aux = image.GetScalarRange()
        if min_scalar is None or min_aux < min_scalar:
            min_scalar = min_aux

        if max_scalar is None or max_aux > max_scalar:
            max_scalar = max_aux

        # 2) Because the convention the VTK follows (1) when the conversion
        #    from VTK to numpy is done the Y axis is flipped with respect to
        #    DICOM slice.
        array = numpy_support.vtk_to_numpy(image.GetPointData().GetScalars())
        if orientation == 'CORONAL':
            array.shape = matrix.shape[0], matrix.shape[2]
            matrix[:, -n-1, :] = array

        elif orientation == 'SAGITTAL':
            array.shape = matrix.shape[0], matrix.shape[1]

            # 3) The direction cosines from DICOM follows the RAI (Right,
            #    Anterior and Inferior) convention whereas InVesalius is
            #    following the RPI convention. The X axis is increasing from
            #    Posterior (P) to Anterior (A) what is the opposite from DICOM
            #    (A->P), so the direction cosine from the X axis from the Image
            #    is inverted. The Y axis from numpy array is flipped with
            #    respect to the DICOM slice, and so is the direction cosine from
            #    Y axis.
            #
            # TODO: Apply the same logic from SAGITTAL to Coronal and Axial.

            if d[2] == 1: # stacking from right to left
                matrix[:, :, n] = array[::-d[0], ::-d[1]]
            
            else: # stacking from left to right
                matrix[:, :, -n-1] = array[::-d[0], ::-d[1]]

        else:
            array.shape = matrix.shape[1], matrix.shape[2]
            matrix[n] = array
        update_progress(cont,message)
        cont += 1

    matrix.flush()
    scalar_range = min_scalar, max_scalar

    return matrix, scalar_range, temp_file


def analyze2mmap(analyze):
    data = analyze.get_data()
    header = analyze.get_header()
    temp_file = tempfile.mktemp()

    # Sagital
    if header['orient'] == 2:
        print "Orientation Sagital"
        shape = tuple([data.shape[i] for i in (1, 2, 0)])
        matrix = numpy.memmap(temp_file, mode='w+', dtype=data.dtype, shape=shape)
        for n, slice in enumerate(data):
            matrix[:,:, n] = slice

    # Coronal
    elif header['orient'] == 1:
        print "Orientation coronal"
        shape = tuple([data.shape[i] for i in (1, 0, 2)])
        matrix = numpy.memmap(temp_file, mode='w+', dtype=data.dtype, shape=shape)
        for n, slice in enumerate(data):
            matrix[:,n,:] = slice

    # AXIAL
    elif header['orient'] == 0:
        print "no orientation"
        shape = tuple([data.shape[i] for i in (0, 1, 2)])
        matrix = numpy.memmap(temp_file, mode='w+', dtype=data.dtype, shape=shape)
        for n, slice in enumerate(data):
            matrix[n] = slice

    else:
        print "Orientation Sagital"
        shape = tuple([data.shape[i] for i in (1, 2, 0)])
        matrix = numpy.memmap(temp_file, mode='w+', dtype=data.dtype, shape=shape)
        for n, slice in enumerate(data):
            matrix[:,:, n] = slice

    matrix.flush()
    return matrix, temp_file
