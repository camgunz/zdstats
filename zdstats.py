import os, sys, json, time, httplib, datetime, operator, subprocess, StringIO

from PySide.QtCore import *
from PySide.QtGui import *

from ZDStack import set_configfile
from ZDStack.Utils import get_event_from_line, resolve_path, \
                          timedelta_in_seconds

APP_AUTHOR = 'Charlie Gunyon'
APP_NAME = 'ZDStats'
IDL_HOST = 'www.intldoomleague.org'
IDL_PORT = 80

def fix_slashes(s):
    return s.replace('/', '\\')

def server_from_dict(name, d):
    return Server(name, d['address'], d['password'])

def get_datetime_filename(extension=None):
    now = datetime.datetime.now()
    if extension:
        return '.'.join((now.strftime('zdstats-%Y%m%d_%H%M%S'), extension))
    else:
        return now.strftime('zdstats-%Y%m%d_%H%M%S')

class InputLog(object):

    def __init__(self, filename):
        self.fobj = open(filename)

    def get_line(self):
        return self.fobj.readline().rstrip('\r\n')

    def close(self):
        self.fobj.close()

class OutputLog(object):

    def __init__(self, filename):
        self.fobj = open(filename, 'wb')
        self.fobj.write('{"events": [\n')
        self.first_event = True

    def write(self, s):
        if self.first_event:
            self.first_event = False
        else:
            self.fobj.write(',\n')
        self.fobj.write('    ')
        self.fobj.write(s)
        self.fobj.flush()

    def close(self):
        self.fobj.write('\n]}\n')
        self.fobj.close()

class Server(object):

    def __init__(self, name, address, password):
        self.name = name
        self.password = password
        if address.startswith('zds://'):
            self.address = address[6:]
        else:
            self.address = address

    def __str__(self):
        return self.name

    __unicode__ = __str__

    def __repr__(self):
        return 'Server(%r, %r, %r)' % (self.name, self.address, self.password)

class ServerListModel(QAbstractListModel):

    def __init__(self, servers=None):
        QAbstractListModel.__init__(self)
        self.icon_provider = None
        self.servers = servers or list()

    def rowCount(self, parent=QModelIndex()):
        return len(self.servers)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.servers[index.row()].name
        else:
            return None

    def headerData(self, index, value, role=Qt.DisplayRole):
        return QVariant()

    def setData(self, index, value, role=Qt.EditRole):
        pass # [CG] Can't edit the server list.

    def flags(self, index):
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

class ServerListView(QListView):

    def __init__(self, *args, **kwargs):
        QListView.__init__(self, *args, **kwargs)
        self.selectedServer = None

    @property
    def rowCount(self):
        model = self.model()
        if model:
            return model.rowCount()
        return 0

    @property
    def servers(self):
        return sorted(self.model().servers, key=operator.attrgetter('name'))

    def setModel(self, model):
        QListView.setModel(self, model)
        self.selectedRows = set(range(self.rowCount))

    def selectionChanged(self, selected, deselected):
        QListView.selectionChanged(self, selected, deselected)
        selected_servers = set([x.row() for x in self.selectedIndexes()])
        if selected_servers:
            selected_server_index = list(selected_servers)[0]
            self.selectedServer = self.servers[selected_server_index]
        else:
            self.selectedServer = None

class MainWindow(QMainWindow):

    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle(APP_NAME)
        self.mainLayout = QHBoxLayout()
        self.leftLayout = QVBoxLayout()
        self.rightLayout = QVBoxLayout()
        self.zdaemonLayout = QHBoxLayout()
        self.outputFolderLayout = QHBoxLayout()
        self.wadFolderLayout = QHBoxLayout()
        self.demoLayout = QHBoxLayout()
        self.serverListLayout = QVBoxLayout()
        self.mainPanel = QWidget()
        self.leftPanel = QWidget()
        self.rightPanel = QWidget()
        self.zdaemonPanel = QWidget()
        self.outputFolderPanel = QWidget()
        self.wadFolderPanel = QWidget()
        self.demoPanel = QWidget()
        self.serverPanel = QWidget()
        self.zdaemonPathLabel = QLabel('Path to ZDaemon:')
        self.zdaemonPathInput = QLineEdit()
        self.zdaemonPathInput.setReadOnly(True)
        self.zdaemonBrowseButton = QPushButton('Browse')
        self.zdaemonLayout.addWidget(self.zdaemonPathLabel)
        self.zdaemonLayout.addWidget(self.zdaemonPathInput)
        self.zdaemonLayout.addWidget(self.zdaemonBrowseButton)
        self.zdaemonPanel.setLayout(self.zdaemonLayout)
        self.outputFolderLabel = QLabel('Output Folder:')
        self.outputFolderInput = QLineEdit()
        self.outputFolderInput.setReadOnly(True)
        self.outputFolderBrowseButton = QPushButton('Browse')
        self.outputFolderOpenButton = QPushButton('Open')
        self.outputFolderLayout.addWidget(self.outputFolderLabel)
        self.outputFolderLayout.addWidget(self.outputFolderInput)
        self.outputFolderLayout.addWidget(self.outputFolderBrowseButton)
        self.outputFolderLayout.addWidget(self.outputFolderOpenButton)
        self.outputFolderPanel.setLayout(self.outputFolderLayout)
        self.wadFolderLabel = QLabel('WAD Folder:')
        self.wadFolderInput = QLineEdit()
        self.wadFolderInput.setReadOnly(True)
        self.wadFolderBrowseButton = QPushButton('Browse')
        self.wadFolderOpenButton = QPushButton('Open')
        self.wadFolderLayout.addWidget(self.wadFolderLabel)
        self.wadFolderLayout.addWidget(self.wadFolderInput)
        self.wadFolderLayout.addWidget(self.wadFolderBrowseButton)
        self.wadFolderLayout.addWidget(self.wadFolderOpenButton)
        self.wadFolderPanel.setLayout(self.wadFolderLayout)
        self.demoPathLabel = QLabel('Load a Demo:')
        self.demoInput = QLineEdit()
        self.demoInput.setReadOnly(True)
        self.demoBrowseButton = QPushButton('Browse')
        self.demoPlayButton = QPushButton('Play')
        self.demoLayout.addWidget(self.demoPathLabel)
        self.demoLayout.addWidget(self.demoInput)
        self.demoLayout.addWidget(self.demoBrowseButton)
        self.demoLayout.addWidget(self.demoPlayButton)
        self.demoPanel.setLayout(self.demoLayout)
        self.serverListModel = ServerListModel()
        self.serverList = ServerListView()
        self.serverList.setModel(self.serverListModel)
        self.serverJoinButton = QPushButton('Join Server')
        self.serverListLayout.addWidget(self.serverList)
        self.serverListLayout.addWidget(self.serverJoinButton)
        self.serverPanel.setLayout(self.serverListLayout)
        self.leftLayout.addWidget(self.zdaemonPanel)
        self.leftLayout.addWidget(self.outputFolderPanel)
        self.leftLayout.addWidget(self.wadFolderPanel)
        self.leftLayout.addWidget(self.demoPanel)
        self.leftPanel.setLayout(self.leftLayout)
        self.rightLayout.addWidget(self.serverPanel)
        self.rightPanel.setLayout(self.rightLayout)
        self.mainLayout.addWidget(self.leftPanel)
        self.mainLayout.addWidget(self.rightPanel)
        self.mainPanel.setLayout(self.mainLayout)
        self.setCentralWidget(self.mainPanel)
        self.readSettings()
        self.zdaemonBrowseButton.clicked.connect(self.setZDaemon)
        self.outputFolderBrowseButton.clicked.connect(self.setOutputFolder)
        self.outputFolderOpenButton.clicked.connect(self.openOutputFolder)
        self.wadFolderBrowseButton.clicked.connect(self.setWADFolder)
        self.wadFolderOpenButton.clicked.connect(self.openWADFolder)
        self.demoBrowseButton.clicked.connect(self.loadDemo)
        self.demoPlayButton.clicked.connect(self.playDemo)
        self.serverJoinButton.clicked.connect(self.connectToServer)
        cwd = os.getcwd().decode('utf8')
        config_file = os.path.join(cwd, u'zdstack.ini')
        sio = StringIO.StringIO()
        fobj = open(config_file, 'rb+')
        for line in fobj.readlines():
            if line.startswith('root_folder'):
                sio.write('root_folder = %s\n' % (os.path.join(cwd, 'zdstack')))
            else:
                sio.write(line)
        fobj.seek(0)
        fobj.write(sio.getvalue())
        fobj.flush()
        fobj.close()
        set_configfile(config_file.encode('utf8'))
        try:
            self.seasonWAD = None
            self.canConnectToServers = True
            self.fetchServersAndLoadWAD()
            self.statusMessage('Ready.')
        except Exception, e:
            self.statusMessage(' - '.join((
                str(e), 'cannot connect to servers.'
            )))
            self.canConnectToServers = False

    def statusMessage(self, s):
        self.statusBar().showMessage(s)

    def fetchServersAndLoadWAD(self):
        error = False
        error_code = None
        conn = httplib.HTTPConnection(IDL_HOST, IDL_PORT)
        conn.request('GET', '/info/servers', headers={
            'accept': 'application/json'
        })
        response = conn.getresponse()
        if response.status != 200:
            raise Exception('Error contacting %s:%d: %d' % (
                IDL_HOST, IDL_PORT, response.status
            ))
        servers = sorted(json.loads(response.read())['servers'].items())
        self.serverListModel.beginResetModel()
        self.serverListModel.servers = [
            server_from_dict(name, d) for name, d in servers
        ]
        self.serverListModel.endResetModel()
        conn.request('GET', '/info/season_wad', headers={
            'accept': 'application/json'
        })
        response = conn.getresponse()
        if response.status != 200:
            raise Exception('Error contacting %s:%d: %d' % (
                IDL_HOST, IDL_PORT, response.status
            ))
        server_wad = json.loads(response.read()).get('wad', None)
        if not server_wad:
            raise Exception('Bad JSON from idl.org')
        self.seasonWAD = server_wad

    def closeEvent(self, event):
        self.writeSettings()
        event.accept()

    def readSettings(self):
        settings = QSettings(APP_AUTHOR, APP_NAME)
        pos = settings.value('pos', QPoint(200, 200))
        size = settings.value('size', QSize(800, 240))
        zdaemon = settings.value('zdaemon', None)
        output_folder = settings.value('output_folder', None)
        wad_folder = settings.value('wad_folder', None)
        self.resize(QSize(800, 240))
        self.move(pos)
        if zdaemon:
            self.zdaemonPathInput.setText(zdaemon)
        if output_folder:
            self.outputFolderInput.setText(output_folder)
        if wad_folder:
            self.wadFolderInput.setText(wad_folder)

    def writeSettings(self):
        settings = QSettings(APP_AUTHOR, APP_NAME)
        settings.setValue('pos', self.pos())
        settings.setValue('size', self.size())
        zdaemon = self.zdaemonPathInput.text()
        output_folder = self.outputFolderInput.text()
        wad_folder = self.wadFolderInput.text()
        if zdaemon:
            settings.setValue('zdaemon', zdaemon)
        if output_folder:
            settings.setValue('output_folder', output_folder)
        if wad_folder:
            settings.setValue('wad_folder', wad_folder)

    def setZDaemon(self):
        filename, filtr = QFileDialog.getOpenFileName(
            self,
            'Set Path to ZDaemon',
            '.',
            'Programs (*.exe);;All files (*.*)'
        )
        if filename:
            filename = fix_slashes(filename)
            self.statusMessage('Set ZDaemon executable to "%s".' % (filename))
            self.zdaemonPathInput.setText(filename)

    def setWADFolder(self):
        foldername = QFileDialog.getExistingDirectory(
            self, 'Select WAD Folder', '.'
        )
        if foldername:
            self.wadFolderInput.setText(foldername)
            self.statusMessage('Set WAD folder to "%s".' % (foldername))

    def openWADFolder(self):
        wad_folder = self.wadFolderInput.text()
        if wad_folder:
            os.startfile(wad_folder)
            self.statusMessage('Opening WAD folder "%s".' % (wad_folder))
        else:
            self.statusMessage('No WAD folder set.')

    def setOutputFolder(self):
        foldername = QFileDialog.getExistingDirectory(
            self, 'Select Output Folder', '.'
        )
        if foldername:
            self.outputFolderInput.setText(foldername)
            self.statusMessage('Set output folder to "%s".' % (foldername))

    def openOutputFolder(self):
        output_folder = self.outputFolderInput.text()
        if output_folder:
            os.startfile(output_folder)
            self.statusMessage('Opening output folder "%s".' % (output_folder))
        else:
            self.statusMessage('No output folder set.')

    def loadDemo(self):
        filename, filtr = QFileDialog.getOpenFileName(
            self,
            'Open ZDaemon Demo',
            '.',
            'ZDaemon Demo File (*.zdo);;All files (*.*)'
        )
        if filename:
            filename = fix_slashes(filename)
            self.demoInput.setText(filename)
            self.statusMessage('Loaded demo "%s".' % (filename))

    def getStats(self, zdaemon_log_path):
        from ZDStack.ZDSRegexps import get_client_regexps
        # [CG] We can safely assume the output folder input field is populated
        #      because this function is only called after the field is checked.
        event_log_path = os.path.join(
            self.outputFolderInput.text(),
            get_datetime_filename(extension='json')
        )
        while not os.path.isfile(zdaemon_log_path):
            time.sleep(1)
        input_logfile = InputLog(zdaemon_log_path)
        output_logfile = OutputLog(event_log_path)
        regexps = get_client_regexps()
        epoch = datetime.datetime(1970, 1, 1)
        while 1:
            if self.zdaemon_pobj.poll() is not None:
                output_logfile.close()
                self.statusMessage('Events saved to %s.' % (event_log_path))
                break
            line = input_logfile.get_line()
            if line:
                e = get_event_from_line(line, regexps)
                if e and (e.category != 'command' or e.type == 'map_change'):
                    td = e.dt - epoch
                    ts = '%s.%s' % (timedelta_in_seconds(td), td.microseconds)
                    output_logfile.write(json.dumps(dict(
                        timestamp=ts,
                        type=e.type,
                        data=e.data,
                        category=e.category
                    )))
            else:
                time.sleep(.027)

    def launchZDaemon(self, extra_args=None):
        zdaemon = self.zdaemonPathInput.text()
        if not zdaemon:
            self.statusMessage('ZDaemon path not set.')
            return
        output_folder = self.outputFolderInput.text()
        if not output_folder:
            self.statusMessage('Output folder not set.')
            return
        wad_folder = self.wadFolderInput.text()
        if not wad_folder:
            self.statusMessage('WAD folder not set.')
            return
        iwad_path = os.path.join(wad_folder, 'doom2.wad')
        if not os.path.isfile(iwad_path):
            self.statusMessage('doom2.wad not found in %s.' % (wad_folder))
            return
        zdaemon_log_file = get_datetime_filename(extension='txt')
        zdaemon_log_path = os.path.join(output_folder, zdaemon_log_file)
        zvox_wad_path = os.path.join(wad_folder, 'zvox2.wad')
        cmd_args = [
            zdaemon,
            '-iwad', iwad_path,
            '-file', zvox_wad_path,
            '+logfile', zdaemon_log_path
        ]
        if extra_args:
            cmd_args.extend(extra_args)
        self.statusMessage('Launching ZDaemon.')
        print ' '.join(cmd_args)
        self.zdaemon_pobj = subprocess.Popen(cmd_args)
        self.statusMessage('Gathering events.')
        self.getStats(zdaemon_log_path)

    def playDemo(self):
        demo_path = self.demoInput.text()
        if not demo_path:
            self.statusMessage('Demo file not selected.')
            return
        wad_folder = self.wadFolderInput.text()
        if not wad_folder:
            self.statusMessage('WAD folder not set.')
            return
        demo_file = os.path.basename(demo_path).lower()
        args = ['+netplay', demo_path]
        wads = [f for f in os.listdir(wad_folder) if f.lower().endswith('wad')]
        for wad in wads:
            if wad[:-4].lower() in demo_file:
                wad_path = os.path.join(wad_folder, wad)
                args.extend(['-file', wad_path])
        if '-file' not in args:
            self.statusMessage(
                'No WADs indicated in demo filename, rename it appropriately.'
            )
            return
        self.launchZDaemon(args)

    def connectToServer(self):
        output_folder = self.outputFolderInput.text()
        if not output_folder:
            self.statusMessage('Output folder not set.')
            return
        server = self.serverList.selectedServer
        if not server:
            self.statusMessage('No server selected.')
            return
        wad_folder = self.wadFolderInput.text()
        if not wad_folder:
            self.statusMessage('WAD folder not set.')
            return
        demo_path = os.path.join(output_folder, get_datetime_filename('zdo'))
        idl_wad_path = os.path.join(wad_folder, self.seasonWAD)
        self.launchZDaemon((
            '-connect', server.address,
            '-file', idl_wad_path,
            '-netrecord', demo_path,
            '+password', server.password
        ))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

