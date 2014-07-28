import wx
import constants as const
from wx.lib.pubsub import pub as Publisher
import session as ses
from language_dialog import ComboBoxLanguage

ID = wx.NewId()

try:
    from agw import flatnotebook as fnb
    AGW = 1
except ImportError: # if it's not there locally, try the wxPython lib.
    import wx.lib.agw.flatnotebook as fnb
    AGW = 0

class Preferences(wx.Dialog):

    def __init__( self, parent, id = ID, title = _("Preferences"), size=wx.DefaultSize,\
                                pos=wx.DefaultPosition, style=wx.DEFAULT_DIALOG_STYLE):
    
        pre = wx.PreDialog()
        pre.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
        pre.Create(parent, ID, title, pos, size, style)

        self.PostCreate(pre)

        sizer = wx.BoxSizer(wx.VERTICAL)
    
        bookStyle = fnb.FNB_NODRAG | fnb.FNB_NO_NAV_BUTTONS | fnb.FNB_NO_X_BUTTON

        if AGW:
            self.book = fnb.FlatNotebook(self, wx.ID_ANY, agwStyle=bookStyle)
        else:
            self.book = fnb.FlatNotebook(self, wx.ID_ANY, agwStyle=bookStyle)
            
        sizer.Add(self.book, 80, wx.EXPAND|wx.ALL)
        
        self.pnl_viewer3d = Viewer3D(self)
        self.pnl_language = Language(self)

        self.book.AddPage(self.pnl_viewer3d, _("Visualization"))
        self.book.AddPage(self.pnl_language, _("Language"))

        line = wx.StaticLine(self, -1, size=(20,-1), style=wx.LI_HORIZONTAL)
        sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP, 5)

        btnsizer = wx.StdDialogButtonSizer()
        
        btn = wx.Button(self, wx.ID_OK)
        btnsizer.AddButton(btn)
    
        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)

        btnsizer.Realize()
        
        sizer.AddSizer(btnsizer, 10, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP|wx.BOTTOM, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.LoadPreferences, 'Load Preferences')


    def GetPreferences(self):
        values = {}
        lang = self.pnl_language.GetSelection()
        viewer = self.pnl_viewer3d.GetSelection()
        values.update(lang)
        values.update(viewer)
        return values

    def LoadPreferences(self, pub_evt):
        se = ses.Session()
        values = {const.RENDERING:se.rendering,
                  const.SURFACE_INTERPOLATION:se.surface_interpolation,
                  const.LANGUAGE:se.language
                }

        self.pnl_viewer3d.LoadSelection(values)
        self.pnl_language.LoadSelection(values)
    


class Viewer3D(wx.Panel):

    def __init__(self, parent):

        wx.Panel.__init__(self, parent)

        
        box_visualization = wx.StaticBox(self, -1, _("Surface"))
        bsizer = wx.StaticBoxSizer(box_visualization, wx.VERTICAL)

        lbl_inter = wx.StaticText(self, -1, _("Interpolation "))
        bsizer.Add(lbl_inter, 0, wx.TOP|wx.LEFT, 10)

        rb_inter = self.rb_inter = wx.RadioBox(self, -1, "", wx.DefaultPosition, wx.DefaultSize,
                    ['Flat','Gouraud','Phong'], 3, wx.RA_SPECIFY_COLS | wx.NO_BORDER)

        bsizer.Add(rb_inter, 0, wx.TOP|wx.LEFT, 0)

        box_rendering = wx.StaticBox(self, -1, _("Volume rendering"))
        bsizer_ren = wx.StaticBoxSizer(box_rendering, wx.VERTICAL)

        lbl_rendering = wx.StaticText(self, -1, _("Rendering"))
        bsizer_ren.Add(lbl_rendering, 0, wx.TOP | wx.LEFT, 10)
        
        rb_rendering = self.rb_rendering = wx.RadioBox(self, -1, "", wx.DefaultPosition, wx.DefaultSize,
                    ['CPU', _(u'GPU (NVidia video cards only)')], 2, wx.RA_SPECIFY_COLS | wx.NO_BORDER)

        bsizer_ren.Add(rb_rendering, 0, wx.TOP | wx.LEFT, 0)
        border = wx.BoxSizer(wx.VERTICAL)
        border.Add(bsizer, 50, wx.EXPAND|wx.ALL, 10)
        border.Add(bsizer_ren, 50, wx.EXPAND|wx.ALL, 10)
        self.SetSizer(border)

        border.Fit(self)


    def GetSelection(self):
        
        options = {const.RENDERING:self.rb_rendering.GetSelection(), 
                    const.SURFACE_INTERPOLATION:self.rb_inter.GetSelection()}

        return options

    def LoadSelection(self, values):
        rendering = values[const.RENDERING]
        surface_interpolation = values[const.SURFACE_INTERPOLATION]

        self.rb_rendering.SetSelection(int(rendering))
        self.rb_inter.SetSelection(int(surface_interpolation))

class Language(wx.Panel):

    def __init__(self, parent):

        wx.Panel.__init__(self, parent)
        
        self.lg = lg = ComboBoxLanguage(self)
        self.cmb_lang = cmb_lang = lg.GetComboBox()
        self.cmb_lang.Bind(wx.EVT_COMBOBOX, self.OnCombo)

        box = wx.StaticBox(self, -1, _("Language"))
        bsizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        
        text = wx.StaticText(self, -1, _("Language settings will be applied \n the next time InVesalius starts."))
        bsizer.Add(cmb_lang, 0, wx.TOP|wx.CENTER, 20)
        bsizer.Add(text, 0, wx.TOP|wx.CENTER, 10) 

        border = wx.BoxSizer()
        border.Add(bsizer, 1, wx.EXPAND|wx.ALL, 20)
        self.SetSizer(border)

        border.Fit(self)

    def GetSelection(self):
        locales = self.lg.GetLocalesKey()
        options = {const.LANGUAGE:locales[self.idx]}
        return options

    def LoadSelection(self, values):
        language = values[const.LANGUAGE]
        locales = self.lg.GetLocalesKey()
        selection = locales.index(language)

        if wx.VERSION > (2, 9):
            self.cmb_lang.Select(int(selection))
        else:
            self.cmb_lang.SetSelection(int(selection))

        self.idx = selection

    def OnCombo(self, evt):
        self.idx = evt.GetInt()
