# -*- coding: utf-8 -*-
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

import sys
import weakref

import numpy as np
import wx
import vtk

from weakrefmethod import WeakMethod

from invesalius.data import converters
from wx.lib.pubsub import pub as Publisher


class CanvasEvent:
    def __init__(self, pos, viewer, renderer):
        self.position = pos
        self.viewer = viewer
        self.renderer = renderer


class CanvasRendererCTX:
    def __init__(self, viewer, evt_renderer, canvas_renderer, orientation=None):
        """
        A Canvas to render over a vtktRenderer.

        Params:
            evt_renderer: a vtkRenderer which this class is going to watch for
                any render event to update the canvas content.
            canvas_renderer: the vtkRenderer where the canvas is going to be
                added.

        This class uses wx.GraphicsContext to render to a vtkImage.

        TODO: Verify why in Windows the color are strange when using transparency.
        TODO: Add support to evento (ex. click on a square)
        """
        self.viewer = viewer
        self.canvas_renderer = canvas_renderer
        self.evt_renderer = evt_renderer
        self._size = self.canvas_renderer.GetSize()
        self.draw_list = []
        self.orientation = orientation
        self.gc = None
        self.last_cam_modif_time = -1
        self.modified = True
        self._drawn = False
        self._init_canvas()

        self._over_obj = None
        self._drag_obj = None

        self._callback_events = {
            'LeftButtonPressEvent': [],
            'LeftButtonReleaseEvent': [],
            'MouseMoveEvent': [],
        }

        self._bind_events()

    def _bind_events(self):
        iren = self.viewer.interactor
        iren.Bind(wx.EVT_MOTION, self.OnMouseMove)
        iren.Bind(wx.EVT_LEFT_DOWN, self.OnLeftButtonPress)
        iren.Bind(wx.EVT_LEFT_UP, self.OnLeftButtonRelease)
        self.canvas_renderer.AddObserver("StartEvent", self.OnPaint)

    def subscribe_event(self, event, callback):
        ref = WeakMethod(callback)
        self._callback_events[event].append(ref)

    def _init_canvas(self):
        w, h = self._size
        self._array = np.zeros((h, w, 4), dtype=np.uint8)

        self._cv_image = converters.np_rgba_to_vtk(self._array)

        self.mapper = vtk.vtkImageMapper()
        self.mapper.SetInputData(self._cv_image)
        self.mapper.SetColorWindow(255)
        self.mapper.SetColorLevel(128)

        self.actor = vtk.vtkActor2D()
        self.actor.SetPosition(0, 0)
        self.actor.SetMapper(self.mapper)
        self.actor.GetProperty().SetOpacity(0.99)

        self.canvas_renderer.AddActor2D(self.actor)

        self.rgb = np.zeros((h, w, 3), dtype=np.uint8)
        self.alpha = np.zeros((h, w, 1), dtype=np.uint8)

        self.bitmap = wx.EmptyBitmapRGBA(w, h)
        self.image = wx.ImageFromBuffer(w, h, self.rgb, self.alpha)

    def _resize_canvas(self, w, h):
        self._array = np.zeros((h, w, 4), dtype=np.uint8)
        self._cv_image = converters.np_rgba_to_vtk(self._array)
        self.mapper.SetInputData(self._cv_image)
        self.mapper.Update()

        self.rgb = np.zeros((h, w, 3), dtype=np.uint8)
        self.alpha = np.zeros((h, w, 1), dtype=np.uint8)

        self.bitmap = wx.EmptyBitmapRGBA(w, h)
        self.image = wx.ImageFromBuffer(w, h, self.rgb, self.alpha)

        self.modified = True

    def remove_from_renderer(self):
        self.canvas_renderer.RemoveActor(self.actor)
        self.evt_renderer.RemoveObservers("StartEvent")

    def Refresh(self):
        print 'Refresh'
        self.modified = True
        self.viewer.interactor.Render()

    def OnMouseMove(self, evt):
        x, y = evt.GetPosition()
        y = self.viewer.interactor.GetSize()[1] - y
        redraw = False

        if self._drag_obj:
            redraw = True
            evt_obj = CanvasEvent((x, y), self.viewer, self.evt_renderer)
            self._drag_obj.mouse_move(evt_obj)
        else:
            for i in self.draw_list:
                try:
                    obj = i.is_over(x, y)
                    self._over_obj = obj
                    if obj:
                        redraw = True
                        break
                except AttributeError:
                    pass

        if redraw:
            #  Publisher.sendMessage('Redraw canvas %s' % self.orientation)
            self.Refresh()

        evt.Skip()

    def OnLeftButtonPress(self, evt):
        x, y = evt.GetPosition()
        y = self.viewer.interactor.GetSize()[1] - y
        evt_obj = CanvasEvent((x, y), self.viewer, self.evt_renderer)
        if self._over_obj and hasattr(self._over_obj, 'mouse_move'):
            self._drag_obj = self._over_obj
            if hasattr(self._over_obj, 'on_select'):
                self._over_obj.on_select(evt_obj)
        else:
            for cb in self._callback_events['LeftButtonPressEvent']:
                if cb() is not None:
                    cb()(evt_obj)
                    break
        evt.Skip()

    def OnLeftButtonRelease(self, evt):
        #  self._over_obj = None
        self._drag_obj = None
        evt.Skip()

    def OnPaint(self, evt, obj):
        size = self.canvas_renderer.GetSize()
        w, h = size
        if self._size != size:
            self._size = size
            self._resize_canvas(w, h)

        cam_modif_time = self.evt_renderer.GetActiveCamera().GetMTime()
        if (not self.modified) and cam_modif_time == self.last_cam_modif_time:
            return

        self.last_cam_modif_time = cam_modif_time

        self._array[:] = 0

        coord = vtk.vtkCoordinate()

        self.image.SetDataBuffer(self.rgb)
        self.image.SetAlphaBuffer(self.alpha)
        self.image.Clear()
        gc = wx.GraphicsContext.Create(self.image)
        if sys.platform != 'darwin':
            gc.SetAntialiasMode(0)

        self.gc = gc

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        #  font.SetWeight(wx.BOLD)
        font = gc.CreateFont(font, (0, 0, 255))
        gc.SetFont(font)

        pen = wx.Pen(wx.Colour(255, 0, 0, 128), 2, wx.SOLID)
        brush = wx.Brush(wx.Colour(0, 255, 0, 128))
        gc.SetPen(pen)
        gc.SetBrush(brush)
        gc.Scale(1, -1)

        for d in self.draw_list:
            d.draw_to_canvas(gc, self)

        gc.Destroy()

        self.gc = None

        if self._drawn:
            self.bitmap = self.image.ConvertToBitmap()
            self.bitmap.CopyToBuffer(self._array, wx.BitmapBufferFormat_RGBA)

        self._cv_image.Modified()
        self.modified = False
        self._drawn = False

    def draw_element_to_array(self, elements, flip=True):
        """
        Draws the given elements to a array.

        Params:
            elements: a list of elements (objects that contains the
                draw_to_canvas method) to draw to a array.
            flip: indicates if it is necessary to flip. In this canvas the Y
                coordinates starts in the bottom of the screen.
        """
        size = self.canvas_renderer.GetSize()
        w, h = size
        image = wx.EmptyImage(w, h)
        image.Clear()

        arr = np.zeros((h, w, 4), dtype=np.uint8)

        gc = wx.GraphicsContext.Create(image)
        if sys.platform != 'darwin':
            gc.SetAntialiasMode(0)
        self.gc = gc

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font = gc.CreateFont(font, (0, 0, 255))
        gc.SetFont(font)

        pen = wx.Pen(wx.Colour(255, 0, 0, 128), 2, wx.SOLID)
        brush = wx.Brush(wx.Colour(0, 255, 0, 128))
        gc.SetPen(pen)
        gc.SetBrush(brush)
        gc.Scale(1, -1)

        for element in elements:
            element.draw_to_canvas(gc, self)

        gc.Destroy()
        self.gc = None

        bitmap = self.image.ConvertToBitmap()
        bitmap.CopyToBuffer(arr, wx.BitmapBufferFormat_RGBA)

        if flip:
            arr = arr[::-1]

        return arr

    def calc_text_size(self, text, font=None):
        """
        Given an unicode text and a font returns the width and height of the
        rendered text in pixels.

        Params:
            text: An unicode text.
            font: An wxFont.

        Returns:
            A tuple with width and height values in pixels
        """
        if self.gc is None:
            return None
        gc = self.gc

        if font is None:
            font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)

        _font = gc.CreateFont(font)
        gc.SetFont(_font)
        w, h = gc.GetTextExtent(text)
        return w, h

    def draw_line(self, pos0, pos1, arrow_start=False, arrow_end=False, colour=(255, 0, 0, 128), width=2, style=wx.SOLID):
        """
        Draw a line from pos0 to pos1

        Params:
            pos0: the start of the line position (x, y).
            pos1: the end of the line position (x, y).
            arrow_start: if to draw a arrow at the start of the line.
            arrow_end: if to draw a arrow at the end of the line.
            colour: RGBA line colour.
            width: the width of line.
            style: default wx.SOLID.
        """
        if self.gc is None:
            return None
        gc = self.gc

        p0x, p0y = pos0
        p1x, p1y = pos1

        p0y = -p0y
        p1y = -p1y

        pen = wx.Pen(wx.Colour(*colour), width, wx.SOLID)
        pen.SetCap(wx.CAP_BUTT)
        gc.SetPen(pen)

        path = gc.CreatePath()
        path.MoveToPoint(p0x, p0y)
        path.AddLineToPoint(p1x, p1y)
        gc.StrokePath(path)

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font = gc.CreateFont(font)
        gc.SetFont(font)
        w, h = gc.GetTextExtent("M")

        p0 = np.array((p0x, p0y))
        p3 = np.array((p1x, p1y))
        if arrow_start:
            v = p3 - p0
            v = v / np.linalg.norm(v)
            iv = np.array((v[1], -v[0]))
            p1 = p0 + w*v + iv*w/2.0
            p2 = p0 + w*v + (-iv)*w/2.0

            path = gc.CreatePath()
            path.MoveToPoint(p0)
            path.AddLineToPoint(p1)
            path.MoveToPoint(p0)
            path.AddLineToPoint(p2)
            gc.StrokePath(path)

        if arrow_end:
            v = p3 - p0
            v = v / np.linalg.norm(v)
            iv = np.array((v[1], -v[0]))
            p1 = p3 - w*v + iv*w/2.0
            p2 = p3 - w*v + (-iv)*w/2.0

            path = gc.CreatePath()
            path.MoveToPoint(p3)
            path.AddLineToPoint(p1)
            path.MoveToPoint(p3)
            path.AddLineToPoint(p2)
            gc.StrokePath(path)

        self._drawn = True

    def draw_circle(self, center, radius=2.5, width=2, line_colour=(255, 0, 0, 128), fill_colour=(0, 0, 0, 0)):
        """
        Draw a circle centered at center with the given radius.

        Params:
            center: (x, y) position.
            radius: float number.
            width: line width.
            line_colour: RGBA line colour
            fill_colour: RGBA fill colour.
        """
        if self.gc is None:
            return None
        gc = self.gc

        pen = wx.Pen(wx.Colour(*line_colour), width, wx.SOLID)
        gc.SetPen(pen)

        brush = wx.Brush(wx.Colour(*fill_colour))
        gc.SetBrush(brush)

        cx, cy = center
        cy = -cy

        path = gc.CreatePath()
        path.AddCircle(cx, cy, radius)
        gc.StrokePath(path)
        gc.FillPath(path)
        self._drawn = True

        return (cx, -cy, radius*2, radius*2)

    def draw_ellipse(self, center, width, height, line_width=2, line_colour=(255, 0, 0, 128), fill_colour=(0, 0, 0, 0)):
        """
        Draw a ellipse centered at center with the given width and height.

        Params:
            center: (x, y) position.
            width: ellipse width (float number).
            height: ellipse height (float number)
            line_width: line width.
            line_colour: RGBA line colour
            fill_colour: RGBA fill colour.
        """
        if self.gc is None:
            return None
        gc = self.gc

        pen = wx.Pen(wx.Colour(*line_colour), line_width, wx.SOLID)
        gc.SetPen(pen)

        brush = wx.Brush(wx.Colour(*fill_colour))
        gc.SetBrush(brush)

        cx, cy = center
        xi = cx - width/2.0
        xf = cx + width/2.0
        yi = cy - height/2.0
        yf = cy + width/2.0

        cx -= width/2.0
        cy += height/2.0
        cy = -cy

        path = gc.CreatePath()
        path.AddEllipse(cx, cy, width, height)
        gc.StrokePath(path)
        gc.FillPath(path)
        self._drawn = True

        return (xi, yi, xf, yf)

    def draw_rectangle(self, pos, width, height, line_colour=(255, 0, 0, 128), fill_colour=(0, 0, 0, 0)):
        """
        Draw a rectangle with its top left at pos and with the given width and height.

        Params:
            pos: The top left pos (x, y) of the rectangle.
            width: width of the rectangle.
            height: heigth of the rectangle.
            line_colour: RGBA line colour.
            fill_colour: RGBA fill colour.
        """
        if self.gc is None:
            return None
        gc = self.gc

        px, py = pos
        py = -py
        gc.SetPen(wx.Pen(wx.Colour(*line_colour)))
        gc.SetBrush(wx.Brush(wx.Colour(*fill_colour)))
        gc.DrawRectangle(px, py, width, height)
        self._drawn = True

    def draw_text(self, text, pos, font=None, txt_colour=(255, 255, 255)):
        """
        Draw text.

        Params:
            text: an unicode text.
            pos: (x, y) top left position.
            font: if None it'll use the default gui font.
            txt_colour: RGB text colour
        """
        if self.gc is None:
            return None
        gc = self.gc

        if font is None:
            font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)

        font = gc.CreateFont(font, txt_colour)
        gc.SetFont(font)

        px, py = pos
        py = -py

        gc.DrawText(text, px, py)
        self._drawn = True

    def draw_text_box(self, text, pos, font=None, txt_colour=(255, 255, 255), bg_colour=(128, 128, 128, 128), border=5):
        """
        Draw text inside a text box.

        Params:
            text: an unicode text.
            pos: (x, y) top left position.
            font: if None it'll use the default gui font.
            txt_colour: RGB text colour
            bg_colour: RGBA box colour
            border: the border size.
        """
        if self.gc is None:
            return None
        gc = self.gc

        if font is None:
            font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)

        _font = gc.CreateFont(font, txt_colour)
        gc.SetFont(_font)
        w, h = gc.GetTextExtent(text)

        px, py = pos

        # Drawing the box
        cw, ch = w + border * 2, h + border * 2
        self.draw_rectangle((px, py), cw, ch, bg_colour, bg_colour)

        # Drawing the text
        tpx, tpy = px + border, py - border
        self.draw_text(text, (tpx, tpy), font, txt_colour)
        self._drawn = True

        return px, py, cw, ch

    def draw_arc(self, center, p0, p1, line_colour=(255, 0, 0, 128), width=2):
        """
        Draw an arc passing in p0 and p1 centered at center.

        Params:
            center: (x, y) center of the arc.
            p0: (x, y).
            p1: (x, y).
            line_colour: RGBA line colour.
            width: width of the line.
        """
        if self.gc is None:
            return None
        gc = self.gc
        pen = wx.Pen(wx.Colour(*line_colour), width, wx.SOLID)
        gc.SetPen(pen)

        c = np.array(center)
        v0 = np.array(p0) - c
        v1 = np.array(p1) - c

        c[1] = -c[1]
        v0[1] = -v0[1]
        v1[1] = -v1[1]

        s0 = np.linalg.norm(v0)
        s1 = np.linalg.norm(v1)

        a0 = np.arctan2(v0[1] , v0[0])
        a1 = np.arctan2(v1[1] , v1[0])

        if (a1 - a0) % (np.pi*2) < (a0 - a1) % (np.pi*2):
            sa = a0
            ea = a1
        else:
            sa = a1
            ea = a0

        path = gc.CreatePath()
        path.AddArc((c[0], c[1]), min(s0, s1), sa, ea)
        gc.StrokePath(path)
        self._drawn = True

    def draw_polygon(self, points, fill=True, line_colour=(255, 255, 255, 255),
                     fill_colour=(255, 255, 255, 255), width=2):

        if self.gc is None:
            return None
        gc = self.gc

        gc.SetPen(wx.Pen(wx.Colour(*line_colour)))
        gc.SetBrush(wx.Brush(wx.Colour(*fill_colour), wx.SOLID))

        if points:
            path = gc.CreatePath()
            px, py = points[0]
            path.MoveToPoint((px, -py))

            for point in points:
                px, py = point
                path.AddLineToPoint((px, -py))

            px, py = points[0]
            path.AddLineToPoint((px, -py))

            gc.StrokePath(path)
            gc.FillPath(path)

            self._drawn = True


class CanvasHandlerBase(object):
    def _3d_to_2d(self, renderer, pos):
        coord = vtk.vtkCoordinate()
        coord.SetValue(pos)
        px, py = coord.GetComputedDoubleDisplayValue(renderer)
        return px, py

    def draw_to_canvas(self, gc, canvas):
        pass

    def is_over(self, x, y):
        xi, yi, xf, yf = self.bbox
        if xi <= x <= xf and yi <= y <= yf:
            print "is_over"
            return self
        return None

class TextBox(CanvasHandlerBase):
    def __init__(self, text, position=(0, 0, 0),
                 text_colour=(0, 0, 0, 255),
                 box_colour=(255, 255, 255, 255)):
        self.text = text
        self.text_colour = text_colour
        self.box_colour = box_colour
        self.position = position

        self.bbox = (0, 0, 0, 0)

        self.visible = True
        self._highlight = False

        self._last_position = (0, 0, 0)

    def set_text(self, text):
        self.text = text

    def draw_to_canvas(self, gc, canvas):
        if self.visible:
            px, py = self._3d_to_2d(canvas.evt_renderer, self.position)

            x, y, w, h = canvas.draw_text_box(self.text, (px, py),
                                              txt_colour=self.text_colour,
                                              bg_colour=self.box_colour)
            if self._highlight:
                print 'highlight'
                rw, rh = canvas.evt_renderer.GetSize()
                print (rw, rh), (x, y), (px, py)
                canvas.draw_rectangle((px, py), w, h,
                                      (255, 0, 0, 25),
                                      (255, 0, 0, 25))

            self.bbox = (x, y - h, x + w, y)

    def is_over(self, x, y):
        xi, yi, xf, yf = self.bbox
        if xi <= x <= xf and yi <= y <= yf:
            self._highlight = True
            return self
        self._highlight = False
        return None

    def mouse_move(self, evt):
        mx, my = evt.position
        x, y, z = evt.viewer.get_coordinate_cursor(mx, my)
        self.position = [i - j + k  for (i, j, k) in zip((x, y, z), self._last_position, self.position)]

        print self.position

        self._last_position = (x, y, z)

        return True

    def on_select(self, evt):
        mx, my = evt.position
        x, y, z = evt.viewer.get_coordinate_cursor(mx, my)
        self._last_position = (x, y, z)


class CircleHandler(CanvasHandlerBase):
    def __init__(self, position, radius=5,
                 line_colour=(255, 255, 255, 255),
                 fill_colour=(0, 0, 0, 0), is_3d=True):

        self.position = position
        self.radius = radius
        self.line_colour = line_colour
        self.fill_colour = fill_colour
        self.bbox = (0, 0, 0, 0)
        self.is_3d = is_3d

        self.visible = True
        self._on_move_function = None

    def on_move(self, evt_function):
        self._on_move_function = WeakMethod(evt_function)

    def draw_to_canvas(self, gc, canvas):
        if self.visible:
            if self.is_3d:
                px, py = self._3d_to_2d(canvas.evt_renderer, self.position)
            else:
                px, py = self.position
            x, y, w, h = canvas.draw_circle((px, py), self.radius,
                                            line_colour=self.line_colour,
                                            fill_colour=self.fill_colour)
            self.bbox = (x - w/2, y - h/2, x + w/2, y + h/2)

    def mouse_move(self, evt):
        mx, my = evt.position
        if self.is_3d:
            x, y, z = evt.viewer.get_coordinate_cursor(mx, my)
            self.position = (x, y, z)

        else:
            self.position = mx, my

        if self._on_move_function and self._on_move_function():
            self._on_move_function()(self)

        return True


class Polygon(CanvasHandlerBase):
    def __init__(self, points=None,
                 fill=True,
                 line_colour=(255, 255, 255, 255),
                 fill_colour=(255, 255, 255, 128), width=2,
                 interactive=True, is_3d=True):

        if points is None:
            self.points = []
        else:
            self.points = points

        self.handlers = []

        self._ref_handlers = {}

        self.fill = fill
        self.line_colour = line_colour
        self.fill_colour = fill_colour
        self.width = width
        self.interactive = interactive
        self.is_3d = is_3d

    def draw_to_canvas(self, gc, canvas):
        if self.points:
            if self.is_3d:
                points = [self._3d_to_2d(canvas.evt_renderer, p) for p in self.points]
            else:
                points = self.points
            canvas.draw_polygon(points, self.fill, self.line_colour, self.fill_colour, self.width)

        if self.interactive:
            for handler in self.handlers:
                handler.draw_to_canvas(gc, canvas)

    def append_point(self, point):
        handler = CircleHandler(point, is_3d=self.is_3d)
        handler.on_move(self.on_move_point)
        self.handlers.append(handler)
        self.points.append(point)

        self._ref_handlers[handler] = len(self.points) - 1

    def on_move_point(self, evt):
        px, py = evt.position
        handler = evt
        point = self._ref_handlers[handler]
        self.points[point] = px, py

    def is_over(self, x, y):
        if self.interactive:
            for handler in self.handlers:
                if handler.is_over(x, y):
                    return handler



class Ellipse(CanvasHandlerBase):
    def __init__(self, center,
                 point1, point2,
                 fill=True,
                 line_colour=(255, 255, 255, 255),
                 fill_colour=(255, 255, 255, 128), width=2,
                 interactive=True, is_3d=True):

        self.center = center
        self.point1 = point1
        self.point2 = point2

        self.bbox = (0, 0, 0, 0)

        self.fill = fill
        self.line_colour = line_colour
        self.fill_colour = fill_colour
        self.width = width
        self.interactive = interactive
        self.is_3d = is_3d

        self.handler_1 = CircleHandler(self.point1, is_3d=is_3d)
        self.handler_2 = CircleHandler(self.point2, is_3d=is_3d)

        self.handler_1.on_move(self.on_move_p1)
        self.handler_2.on_move(self.on_move_p2)

        self._on_change_function = None

    def draw_to_canvas(self, gc, canvas):
        if self.is_3d:
            cx, cy = self._3d_to_2d(canvas.evt_renderer, self.center)
            p1x, p1y = self._3d_to_2d(canvas.evt_renderer, self.point1)
            p2x, p2y = self._3d_to_2d(canvas.evt_renderer, self.point2)
        else:
            cx, cy = self.center
            p1x, p1y = self.point1
            p2x, p2y = self.point2

        width = abs(p1x - cx) * 2.0
        height = abs(p2y - cy) * 2.0

        print "ELLIPSE WIDTH HEIGHT", width, height

        self.bbox = canvas.draw_ellipse((cx, cy), width, height,
                                        self.width,
                                        self.line_colour,
                                        self.fill_colour)

        self.handler_1.draw_to_canvas(gc, canvas)
        self.handler_2.draw_to_canvas(gc, canvas)

    def set_point1(self, pos):
        self.point1 = pos
        self.handler_1.position = pos

    def set_point2(self, pos):
        self.point2 = pos
        self.handler_2.position = pos

    def on_change(self, evt_function):
        self._on_change_function = WeakMethod(evt_function)

    def on_move_p1(self, evt):
        pos = evt.position
        self.set_point1(pos)

        if self._on_change_function and self._on_change_function():
            self._on_change_function()()

    def on_move_p2(self, evt):
        pos = evt.position
        self.set_point2(pos)

        if self._on_change_function and self._on_change_function():
            self._on_change_function()()

    def is_over(self, x, y):
        xi, yi, xf, yf = self.bbox

        if self.handler_1.is_over(x, y):
            return self.handler_1
        elif self.handler_2.is_over(x, y):
            return self.handler_2
        elif xi <= x <= xf and yi <= y <= yf:
            return self

    def mouse_move(self, evt):
        mx, my = evt.position
        if self.is_3d:
            x, y, z = evt.viewer.get_coordinate_cursor(mx, my)
            new_pos = (x, y, z)
        else:
            new_pos = mx, my

        diff = [i-j for i,j in zip(new_pos, self._last_position)]

        self.center = tuple((i+j for i,j in zip(diff, self.center)))
        self.set_point1(tuple((i+j for i,j in zip(diff, self.point1))))
        self.set_point2(tuple((i+j for i,j in zip(diff, self.point2))))

        self._last_position = new_pos

        if self._on_change_function and self._on_change_function():
            self._on_change_function()()

        return True

    def on_select(self, evt):
        mx, my = evt.position
        if self.is_3d:
            x, y, z = evt.viewer.get_coordinate_cursor(mx, my)
            self._last_position = (x, y, z)
        else:
            self._last_position = (mx, my)
