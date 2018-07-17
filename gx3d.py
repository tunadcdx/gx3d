itemsbl_info = {
    "name": "Gearoenix 3D Blender",
    "author": "Hossein Noroozpour",
    "version": (3, 0),
    "blender": (2, 7, 5),
    "api": 1,
    "location": "File > Export",
    "description": "Export several scene into a Gearoenix 3D file format.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export",
}

import ctypes
import enum
import io
import math
import os
import subprocess
import sys
import tempfile

import bpy
import bpy_extras
import mathutils

TYPE_BOOLEAN = ctypes.c_uint8
TYPE_BYTE = ctypes.c_uint8
TYPE_FLOAT = ctypes.c_float
TYPE_U64 = ctypes.c_uint64
TYPE_U32 = ctypes.c_uint32
TYPE_U16 = ctypes.c_uint16
TYPE_U8 = ctypes.c_uint8

STRING_CUTOFF = 'cutoff'

DEBUG_MODE = True

EPSILON = 0.0001


class Gearoenix:

    ENGINE_GEAROENIX = 0
    ENGINE_VULKUST = 1

    EXPORT_GEAROENIX = False
    EXPORT_VULKUST = False
    EXPORT_FILE_PATH = None

    GX3D_FILE = None
    CPP_FILE = None
    RUST_FILE = None

    last_id = 1024

    @classmethod
    def register(cls, c):
        exec("cls." + c.__name__ + " = c")


@Gearoenix.register
def terminate(*msgs):
    msg = ""
    for m in msgs:
        msg += str(m) + " "
    print("Fatal error: " + msg)
    raise Exception(msg)


@Gearoenix.register
def initialize_pathes():
    Gearoenix.GX3D_FILE = open(
        Gearoenix.EXPORT_FILE_PATH, mode='wb')
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE = open(
            Gearoenix.EXPORT_FILE_PATH + ".rs", mode='w')
    if Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE = open(
            Gearoenix.EXPORT_FILE_PATH + ".hpp", mode='w')


@Gearoenix.register
def log_info(*msgs):
    if DEBUG_MODE:
        msg = ""
        for m in msgs:
            msg += str(m) + " "
        print("Info: " + msg)


@Gearoenix.register
def write_float(f):
    Gearoenix.GX3D_FILE.write(TYPE_FLOAT(f))


@Gearoenix.register
def write_u64(n):
    Gearoenix.GX3D_FILE.write(TYPE_U64(n))


@Gearoenix.register
def write_u32(n):
    Gearoenix.GX3D_FILE.write(TYPE_U32(n))


@Gearoenix.register
def write_u16(n):
    Gearoenix.GX3D_FILE.write(TYPE_U16(n))


@Gearoenix.register
def write_u8(n):
    Gearoenix.GX3D_FILE.write(TYPE_U8(n))


@Gearoenix.register
def write_instances_ids(inss):
    write_u64(len(inss))
    for ins in inss:
        write_u64(ins.my_id)


@Gearoenix.register
def write_vector(v, element_count=3):
    for i in range(element_count):
        write_float(v[i])


@Gearoenix.register
def write_matrix(matrix):
    for i in range(0, 4):
        for j in range(0, 4):
            write_float(matrix[j][i])


@Gearoenix.register
def write_u32_array(arr):
    write_u64(len(arr))
    for i in arr:
        write_u32(i)


@Gearoenix.register
def write_u64_array(arr):
    write_u64(len(arr))
    for i in arr:
        write_u64(i)


@Gearoenix.register
def write_bool(b):
    data = 0
    if b:
        data = 1
    Gearoenix.GX3D_FILE.write(TYPE_BOOLEAN(data))


@Gearoenix.register
def file_tell():
    return Gearoenix.GX3D_FILE.tell()


@Gearoenix.register
def limit_check(val, maxval=1.0, minval=0.0, obj=None):
    if val > maxval or val < minval:
        msg = "Out of range value"
        if obj is not None:
            msg += ", in object: " + obj.name
        terminate(msg)


@Gearoenix.register
def uint_check(s):
    try:
        if int(s) >= 0:
            return True
    except ValueError:
        terminate("Type error")
    terminate("Type error")


@Gearoenix.register
def get_origin_name(bobj):
    origin_name = bobj.name.strip().split('.')
    num_dot = len(origin_name)
    if num_dot > 2 or num_dot < 1:
        terminate("Wrong name in:", bobj.name)
    elif num_dot == 1:
        return None
    try:
        int(origin_name[1])
    except:
        terminate("Wrong name in:", bobj.name)
    return origin_name[0]


@Gearoenix.register
def is_zero(f):
    return -EPSILON < f < EPSILON


@Gearoenix.register
def has_transformation(bobj):
    m = bobj.matrix_world
    if bobj.parent is not None:
        m = bobj.parent.matrix_world.inverted() * m
    for i in range(4):
        for j in range(4):
            if i == j:
                if not is_zero(m[i][j] - 1.0):
                    return True
            elif not is_zero(m[i][j]):
                return True
    return False


@Gearoenix.register
def write_string(s):
    bs = bytes(s, 'utf-8')
    write_u64(len(bs))
    for b in bs:
        write_u8(b)


@Gearoenix.register
def const_string(s):
    ss = s.replace("-", "_")
    ss = ss.replace('/', '_')
    ss = ss.replace('.', '_')
    ss = ss.replace('C:\\', '_')
    ss = ss.replace('c:\\', '_')
    ss = ss.replace('\\', '_')
    ss = ss.upper()
    return ss


@Gearoenix.register
def read_file(f):
    return open(f, "rb").read()


@Gearoenix.register
def write_file(f):
    write_u64(len(f))
    Gearoenix.GX3D_FILE.write(f)


@Gearoenix.register
def enum_max_check(e):
    if e == e.MAX:
        terminate('UNEXPECTED')


@Gearoenix.register
def write_start_module(c):
    mod_name = c.__name__
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.write(
            "#[cfg_attr(debug_assertions, derive(Debug))]\n")
        Gearoenix.RUST_FILE.write("#[repr(u64)]\n")
        Gearoenix.RUST_FILE.write("pub enum " + mod_name + " {\n")
    elif Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.write("namespace " + mod_name + "\n{\n")


@Gearoenix.register
def write_name_id(name, item_id):
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.write(
            "    " + name.upper() + " = " + str(int(item_id)) + ",\n")
    elif Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.write(
            "\tconst gearoenix::core::Id " + name + " = " + str(item_id) + ";\n")


@Gearoenix.register
def write_end_modul():
    if Gearoenix.EXPORT_VULKUST:
        Gearoenix.RUST_FILE.write("}\n")
    elif Gearoenix.EXPORT_GEAROENIX:
        Gearoenix.CPP_FILE.write("}\n")


@Gearoenix.register
def find_common_starting(s1, s2):
    s = ''
    l = min(len(s1), len(s2))
    for i in range(l):
        if s1[i] == s2[i]:
            s += s1[i]
        else:
            break
    return s


@Gearoenix.register
class GxTmpFile:
    def __init__(self):
        tmpfile = tempfile.NamedTemporaryFile(delete=False)
        self.filename = tmpfile.name
        tmpfile.close()

    def __del__(self):
        os.remove(self.filename)

    def read(self):
        f = open(self.filename, 'rb')
        d = f.read()
        f.close()
        return d


@Gearoenix.register
class RenderObject:
    # each instance of this class must define:
    #     my_type    int
    # it will add following fiels:
    #     items      dict[name] = instance
    #     name       str
    #     my_id      int
    #     offset     int
    #     bobj       blender-object

    def __init__(self, bobj):
        self.offset = 0
        self.bobj = bobj
        self.my_id = Gearoenix.last_id
        Gearoenix.last_id += 1
        self.name = self.__class__.get_name_from_bobj(bobj)
        if not bobj.name.startswith(self.__class__.get_prefix()):
            terminate("Unexpected name in ", self.__class__.__name__)
        if self.name in self.__class__.items:
            terminate(self.name, "is already in items.")
        self.__class__.items[self.name] = self

    @classmethod
    def get_prefix(cls):
        return cls.__name__.lower() + '-'

    def write(self):
        Gearoenix.write_u64(self.my_type)

    @classmethod
    def write_all(cls):
        items = sorted(cls.items.items(), key=lambda kv: kv[1].my_id)
        for (_, item) in items:
            item.offset = Gearoenix.file_tell()
            item.write()

    @classmethod
    def write_table(cls):
        Gearoenix.write_start_module(cls)
        items = sorted(cls.items.items(), key=lambda kv: kv[1].my_id)
        print("TEST ", items)
        common_starting = ''
        if len(cls.items) > 1:
            for k in cls.items.keys():
                common_starting = Gearoenix.const_string(k)
                break
        for k in cls.items.keys():
            common_starting = Gearoenix.find_common_starting(
                common_starting, Gearoenix.const_string(k))
        Gearoenix.write_u64(len(items))
        for _, item in items:
            Gearoenix.write_u64(item.my_id)
            Gearoenix.write_u64(item.offset)
            name = Gearoenix.const_string(item.name)[len(common_starting):]
            Gearoenix.write_name_id(name, item.my_id)
        Gearoenix.write_end_modul()

    @staticmethod
    def get_name_from_bobj(bobj):
        return bobj.name

    @classmethod
    def read(cls, bobj):
        name = cls.get_name_from_bobj(bobj)
        if not bobj.name.startswith(cls.get_prefix()):
            return None
        if name in cls.items:
            return None
        return cls(bobj)

    @classmethod
    def init(cls):
        cls.items = dict()

    def get_offset(self):
        return self.offset


@Gearoenix.register
class UniRenderObject(Gearoenix.RenderObject):
    # It is going to implement those objects:
    #     Having an origin that their data is is mostly same
    #     Must be kept unique in all object to prevent data redundancy
    # It adds following fields in addition to RenderObject fields:
    #     origin_instance instance

    def __init__(self, bobj):
        self.origin_instance = None
        origin_name = Gearoenix.get_origin_name(bobj)
        if origin_name is None:
            return super().__init__(bobj)
        self.origin_instance = self.__class__.items[origin_name]
        self.name = bobj.name
        self.my_id = self.origin_instance.my_id
        self.my_type = self.origin_instance.my_type
        self.bobj = bobj

    def write(self):
        if self.origin_instance is not None:
            Gearoenix.terminate(
                'This object must not written like this. in', self.name)
        super().write()

    @classmethod
    def read(cls, bobj):
        if not bobj.name.startswith(cls.get_prefix()):
            return None
        origin_name = Gearoenix.get_origin_name(bobj)
        if origin_name is None:
            return super().read(bobj)
        super().read(bpy.data.objects[origin_name])
        return cls(bobj)


@Gearoenix.register
class ReferenceableObject(Gearoenix.RenderObject):
    # It is going to implement those objects:
    #     Have a same data in all object
    # It adds following fields in addition to RenderObject fields:
    #     origin_instance instance

    def __init__(self, bobj):
        self.origin_instance = None
        self.name = self.__class__.get_name_from_bobj(bobj)
        if self.name not in self.__class__.items:
            return super().__init__(bobj)
        self.origin_instance = self.__class__.items[self.name]
        self.my_id = self.origin_instance.my_id
        self.my_type = self.origin_instance.my_type
        self.bobj = bobj

    @classmethod
    def read(cls, bobj):
        if not bobj.name.startswith(cls.get_prefix()):
            return None
        name = cls.get_name_from_bobj(bobj)
        if name not in cls.items:
            return super().read(bobj)
        return cls(bobj)

    def write(self):
        if self.origin_instance is not None:
            Gearoenix.terminate(
                'This object must not written like this. in', self.name)
        super().write()

    def get_offset(self):
        if self.origin_instance is None:
            return self.offset
        return self.origin_instance.offset


@Gearoenix.register
class Audio(Gearoenix.ReferenceableObject):
    TYPE_MUSIC = 1
    TYPE_OBJECT = 2

    @classmethod
    def init(cls):
        super().init()
        cls.MUSIC_PREFIX = cls.get_prefix() + 'music-'
        cls.OBJECT_PREFIX = cls.get_prefix() + 'object-'

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.startswith(self.MUSIC_PREFIX):
            self.my_type = self.TYPE_MUSIC
        elif bobj.startswith(self.OBJECT_PREFIX):
            self.my_type = self.TYPE_OBJECT
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)
        self.file = read_file(self.name)

    def write(self):
        super().write()
        Gearoenix.write_file(self.file)

    @staticmethod
    def get_name_from_bobj(bobj):
        if bobj.type != 'SPEAKER':
            Gearoenix.terminate("Audio must be speaker: ", bobj.name)
        aud = bobj.data
        if aud is None:
            Gearoenix.terminate("Audio is not set in speaker: ", bobj.name)
        aud = aud.sound
        if aud is None:
            Gearoenix.terminate("Sound is not set in speaker: ", bobj.name)
        filepath = aud.filepath.strip()
        if filepath is None or len(filepath) == 0:
            Gearoenix.terminate(
                "Audio is not specified yet in speaker: ", bobj.name)
        if not filepath.endswith(".ogg"):
            Gearoenix.terminate("Use OGG instead of ", filepath)
        return filepath


@Gearoenix.register
class Light(Gearoenix.RenderObject):
    TYPE_SUN = 1

    @classmethod
    def init(cls):
        super().init()
        cls.SUN_PREFIX = cls.get_prefix() + 'sun-'

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.type != 'LAMP':
            Gearoenix.terminate('Light type is incorrect:', bobj.name)
        if bobj.name.startswith(self.SUN_PREFIX):
            self.my_type = self.TYPE_SUN
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)

    def write(self):
        super().write()
        Gearoenix.write_vector(self.bobj.location)
        Gearoenix.write_vector(self.bobj.rotation_euler)
        Gearoenix.write_float(self.bobj['near'])
        Gearoenix.write_float(self.bobj['far'])
        Gearoenix.write_float(self.bobj['size'])
        Gearoenix.write_vector(self.bobj.data.color)


@Gearoenix.register
class Camera(RenderObject):
    TYPE_PERSPECTIVE = 1
    TYPE_ORTHOGRAPHIC = 2

    @classmethod
    def init(cls):
        super().init()
        cls.PERSPECTIVE_PREFIX = cls.get_prefix() + 'perspective-'
        cls.ORTHOGRAPHIC_PREFIX = cls.get_prefix() + 'orthographic-'

    def __init__(self, bobj):
        super().__init__(bobj)
        if self.bobj.type != 'CAMERA':
            Gearoenix.terminate('Camera type is incorrect:', bobj.name)
        if bobj.name.startswith(self.PERSPECTIVE_PREFIX):
            self.my_type = self.TYPE_PERSPECTIVE
            if bobj.data.type != 'PERSP':
                Gearoenix.terminate('Camera type is incorrect:', bobj.name)
        elif bobj.name.startswith(self.ORTHOGRAPHIC_PREFIX):
            self.my_type = self.TYPE_ORTHOGRAPHIC
            if bobj.data.type != 'ORTHO':
                Gearoenix.terminate('Camera type is incorrect:', bobj.name)
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)

    def write(self):
        super().write()
        cam = self.bobj.data
        Gearoenix.write_vector(self.bobj.location)
        Gearoenix.write_vector(self.bobj.rotation_euler)
        Gearoenix.write_float(cam.clip_start)
        Gearoenix.write_float(cam.clip_end)
        if self.my_type == self.TYPE_PERSPECTIVE:
            Gearoenix.write_float(cam.angle_x / 2.0)
        elif self.my_type == self.TYPE_ORTHOGRAPHIC:
            Gearoenix.write_float(cam.ortho_scale / 2.0)
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)


@Gearoenix.register
class Constraint(Gearoenix.RenderObject):
    TYPE_PLACER = 1
    TYPE_TRACKER = 2
    TYPE_SPRING = 3
    TYPE_SPRING_JOINT = 4

    @classmethod
    def init(cls):
        super().init()
        cls.PLACER_PREFIX = cls.get_prefix() + 'placer-'

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.name.startswith(self.PLACER_PREFIX):
            self.my_type = self.TYPE_PLACER
            self.init_placer()
        else:
            Gearoenix.terminate('Unspecified type in:', bobj.name)

    def write(self):
        super().write()
        if self.my_type == self.TYPE_PLACER:
            self.write_placer()
        else:
            terminate('Unspecified type in:', bobj.name)

    def init_placer(self):
        BTYPE = "EMPTY"
        DESC = 'Placer constraint'
        ATT_X_MIDDLE = 'x-middle'  # 0
        ATT_Y_MIDDLE = 'y-middle'  # 1
        ATT_X_RIGHT = 'x-right'  # 2
        ATT_X_LEFT = 'x-left'  # 3
        ATT_Y_UP = 'y-up'  # 4
        ATT_Y_DOWN = 'y-down'  # 5
        ATT_RATIO = 'ratio'
        if self.bobj.type != BTYPE:
            Gearoenix.terminate(
                DESC, "type must be", BTYPE, "in object:", self.bobj.name)
        if len(self.bobj.children) < 1:
            Gearoenix.terminate(
                DESC, "must have more than 0 children, in object:",
                self.bobj.name)
        self.model_children = []
        for c in self.bobj.children:
            ins = Gearoenix.Model.read(c)
            if ins is None:
                Gearoenix.terminate(
                    DESC, "can only have model as its child, in object:",
                    self.bobj.name)
            self.model_children.append(ins)
        self.attrs = [None for i in range(6)]
        if ATT_X_MIDDLE in self.bobj:
            self.check_trans()
            self.attrs[0] = self.bobj[ATT_X_MIDDLE]
        if ATT_Y_MIDDLE in self.bobj:
            self.check_trans()
            self.attrs[1] = self.bobj[ATT_Y_MIDDLE]
        if ATT_X_LEFT in self.bobj:
            self.attrs[2] = self.bobj[ATT_X_LEFT]
        if ATT_X_RIGHT in self.bobj:
            self.attrs[3] = self.bobj[ATT_X_RIGHT]
        if ATT_Y_UP in self.bobj:
            self.attrs[4] = self.bobj[ATT_Y_UP]
        if ATT_Y_DOWN in self.bobj:
            self.attrs[5] = self.bobj[ATT_Y_DOWN]
        if ATT_RATIO in self.bobj:
            self.ratio = self.bobj[ATT_RATIO]
        else:
            self.ratio = None
        self.placer_type = 0
        for i in range(len(self.attrs)):
            if self.attrs[i] is not None:
                self.placer_type |= (1 << i)
        if self.placer_type not in {
                4, 8, 33,
        }:
            Gearoenix.terminate(
                DESC, "must have meaningful combination, in object:",
                self.bobj.name)

    def write_placer(self):
        Gearoenix.write_u64(self.placer_type)
        if self.ratio is not None:
            Gearoenix.write_float(self.ratio)
        if self.placer_type == 4:
            Gearoenix.write_float(self.attrs[2])
        elif self.placer_type == 8:
            Gearoenix.write_float(self.attrs[3])
        elif self.placer_type == 33:
            Gearoenix.write_float(self.attrs[0])
            Gearoenix.write_float(self.attrs[5])
        else:
            Gearoenix.terminate(
                "It is not implemented, in object:", self.bobj.name)
        childrenids = []
        for c in self.model_children:
            childrenids.append(c.my_id)
        childrenids.sort()
        Gearoenix.write_u64_array(childrenids)

    def check_trans(self):
        if Gearoenix.has_transformation(self.bobj):
            Gearoenix.terminate(
                "This object should not have any transformation, in:",
                self.bobj.name)


@Gearoenix.register
class Collider:
    GHOST = 1
    MESH = 2
    PREFIX = 'collider-'
    CHILDREN = []

    def __init__(self, bobj=None):
        if bobj is None:
            if self.MY_TYPE == self.GHOST:
                return
            else:
                terminate("Unexpected bobj is None")
        if not bobj.name.startswith(self.PREFIX):
            terminate("Collider object name is wrong. In:", bobj.name)
        self.bobj = bobj

    def write(self):
        write_u64(self.MY_TYPE)
        pass

    @classmethod
    def read(cls, pbobj):
        collider_object = None
        for bobj in pbobj.children:
            for c in cls.CHILDREN:
                if bobj.name.startswith(c.PREFIX):
                    if collider_object is not None:
                        terminate("Only one collider is acceptable. In model:",
                                  pbobj.name)
                    collider_object = c(bobj)
        if collider_object is None:
            return GhostCollider()
        return collider_object


@Gearoenix.register
class GhostCollider(Collider):
    MY_TYPE = Collider.GHOST
    PREFIX = Collider.PREFIX + 'ghost-'


Collider.CHILDREN.append(GhostCollider)


@Gearoenix.register
class MeshCollider(Collider):
    MY_TYPE = Collider.MESH
    PREFIX = Collider.PREFIX + 'mesh-'

    def __init__(self, bobj):
        super().__init__(bobj)
        self.bobj = bobj
        if bobj.type != 'MESH':
            terminate('Mesh collider must have mesh object type, In model:',
                      bobj.name)
        if has_transformation(bobj):
            terminate('Mesh collider can not have any transformation, in:',
                      bobj.name)
        msh = bobj.data
        self.indices = []
        self.vertices = msh.vertices
        for p in msh.polygons:
            if len(p.vertices) > 3:
                terminate("Object", bobj.name, "is not triangled!")
            for i in p.vertices:
                self.indices.append(i)

    def write(self):
        super().write()
        write_u64(len(self.vertices))
        for v in self.vertices:
            write_vector(v.co)
        write_u32_array(self.indices)


Collider.CHILDREN.append(MeshCollider)


@Gearoenix.register
class Texture(ReferenceableObject):
    TYPE_2D = 1
    TYPE_3D = 2
    TYPE_CUBE = 3
    TYPE_BACKED_ENVIRONMENT = 4
    TYPE_NORMALMAP = 5
    TYPE_SPECULARE = 6

    @classmethod
    def init(cls):
        super().init()
        cls.D2_PREFIX = cls.get_prefix() + "2d-"
        cls.D3_PREFIX = cls.get_prefix() + "3d-"
        cls.CUBE_PREFIX = cls.get_prefix() + "cube-"
        cls.BACKED_ENVIRONMENT_PREFIX = cls.get_prefix() + "bkenv-"
        cls.NORMALMAP_PREFIX = cls.get_prefix() + "nrm-"
        cls.SPECULARE_PREFIX = cls.get_prefix() + "spec-"

    def init_6_face(self):
        if not self.name.endswith('-up.png'):
            terminate('Incorrect 6 face texture:', self.bobj.name)
        base_name = self.name[:len(self.name) - len('-up.png')]
        self.img_up = read_file(self.name)
        self.img_down = read_file(base_name + '-down.png')
        self.img_left = read_file(base_name + '-left.png')
        self.img_right = read_file(base_name + '-right.png')
        self.img_front = read_file(base_name + '-front.png')
        self.img_back = read_file(base_name + '-back.png')

    def write_6_face(self):
        write_file(self.img_up)
        write_file(self.img_down)
        write_file(self.img_left)
        write_file(self.img_right)
        write_file(self.img_front)
        write_file(self.img_back)

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.name.startswith(self.D2_PREFIX):
            self.file = read_file(self.name)
            self.my_type = self.TYPE_2D
        elif bobj.name.startswith(self.D3_PREFIX):
            self.file = read_file(self.name)
            self.my_type = self.TYPE_D3
        elif bobj.name.startswith(self.CUBE_PREFIX):
            self.init_6_face()
            self.my_type = self.TYPE_CUBE
        elif bobj.name.startswith(self.BACKED_ENVIRONMENT_PREFIX):
            self.init_6_face()
            self.my_type = self.TYPE_BACKED_ENVIRONMENT
        elif bobj.name.startswith(self.NORMALMAP_PREFIX):
            self.file = read_file(self.name)
            self.my_type = self.TYPE_NORMALMAP
        elif bobj.name.startswith(self.SPECULARE_PREFIX):
            self.file = read_file(self.name)
            self.my_type = self.TYPE_SPECULARE
        else:
            terminate('Unspecified texture type, in:', bobl.name)

    def write(self):
        super().write()
        if self.my_type == self.TYPE_2D or \
                self.my_type == self.TYPE_3D or \
                self.my_type == self.TYPE_NORMALMAP or \
                self.my_type == self.TYPE_SPECULARE:
            write_file(self.file)
        elif self.my_type == self.TYPE_CUBE or \
                self.my_type == self.TYPE_BACKED_ENVIRONMENT:
            self.write_6_face()
        else:
            terminate('Unspecified texture type, in:', self.bobj.name)

    @staticmethod
    def get_name_from_bobj(bobj):
        filepath = None
        if bobj.type == 'IMAGE':
            img = bobj.image
            if img is None:
                terminate("Image is not set in texture:", bobj.name)
            filepath = bpy.path.abspath(bobj.image.filepath_raw).strip()
        else:
            terminate("Unrecognized type for texture")
        if filepath is None or len(filepath) == 0:
            terminate("Filepass is empty:", bobj.name)
        if not filepath.endswith(".png"):
            terminate("Use PNG for image, in:", filepath)
        return filepath


@Gearoenix.register
class Font(ReferenceableObject):
    TYPE_2D = 1
    TYPE_3D = 2

    @classmethod
    def init(cls):
        super().init()
        cls.D2_PREFIX = cls.get_prefix() + "2d-"
        cls.D3_PREFIX = cls.get_prefix() + "3d-"

    def __init__(self, bobj):
        super().__init__(bobj)
        if bobj.name.startswith(self.D2_PREFIX):
            self.my_type = self.TYPE_2D
        elif bobj.name.startswith(self.D3_PREFIX):
            self.my_type = self.TYPE_D3
        else:
            terminate('Unspecified texture type, in:', bobl.name)
        self.file = read_ttf(self.name)

    def write(self):
        super().write()
        write_file(self.file)

    @staticmethod
    def get_name_from_bobj(bobj):
        filepath = None
        if str(type(bobj)) == "<class 'bpy.types.VectorFont'>":
            filepath = bpy.path.abspath(bobj.filepath).strip()
        else:
            terminate("Unrecognized type for font")
        if filepath is None or len(filepath) == 0:
            terminate("Filepass is empty:", bobj.name)
        if not filepath.endswith(".ttf"):
            terminate("Use TTF for font, in:", filepath)
        return filepath


@Gearoenix.register
class Mesh(UniRenderObject):
    TYPE_BASIC = 1

    def __init__(self, bobj):
        super().__init__(bobj)
        self.my_type = self.TYPE_BASIC
        if bobj.type != 'MESH':
            terminate('Mesh must be of type MESH:', bobj.name)
        if has_transformation(bobj):
            terminate("Mesh must not have any transformation. in:", bobj.name)
        if len(bobj.children) != 0:
            terminate("Mesh can not have children:", bobj.name)
        self.shd = Shading(bobj.material_slots[0].material)
        if self.origin_instance is not None:
            if not self.shd.has_same_attrs(self.origin_instance.shd):
                terminate("Different mesh attributes, in: " + bobj.name)
            return
        if bobj.parent is not None:
            terminate("Mesh can not have parent:", bobj.name)
        msh = bobj.data
        nrm = self.shd.needs_normal()
        uv = self.shd.needs_uv()
        vertices = dict()
        last_index = 0
        for p in msh.polygons:
            if len(p.vertices) > 3:
                terminate("Object " + bobj.name + " is not triangled!")
            for i, li in zip(p.vertices, p.loop_indices):
                vertex = []
                v = msh.vertices[i].co
                vertex.append(v[0])
                vertex.append(v[1])
                vertex.append(v[2])
                if nrm:
                    normal = msh.vertices[i].normal.normalized()
                    vertex.append(normal[0])
                    vertex.append(normal[1])
                    vertex.append(normal[2])
                if uv:
                    uv_lyrs = msh.uv_layers
                    if len(uv_lyrs) > 1 or len(uv_lyrs) < 1:
                        terminate("Unexpected number of uv layers in ",
                                  bobj.name)
                    texco = uv_lyrs.active.data[li].uv
                    vertex.append(texco[0])
                    vertex.append(1.0 - texco[1])
                vertex = tuple(vertex)
                if vertex in vertices:
                    vertices[vertex].append(last_index)
                else:
                    vertices[vertex] = [last_index]
                last_index += 1
        self.indices = [0 for _ in range(last_index)]
        self.vertices = []
        last_index = 0
        for vertex, index_list in vertices.items():
            self.vertices.append(vertex)
            for i in index_list:
                self.indices[i] = last_index
            last_index += 1

    def write(self):
        super().write()
        write_u64(len(self.vertices[0]))
        write_u64(len(self.vertices))
        for vertex in self.vertices:
            for e in vertex:
                write_float(e)
        write_u32_array(self.indices)


class Occlusion:
    PREFIX = 'occlusion-'

    def __init__(self, bobj):
        if bobj.empty_draw_type != 'SPHERE':
            terminate("The only acceptable shape for an occlusion is " +
                      "sphere. in: " + bobj.name)
        center = bobj.matrix_world * mathutils.Vector((0.0, 0.0, 0.0))
        radius = bobj.empty_draw_size
        radius = mathutils.Vector((radius, radius, radius))
        radius = bobj.matrix_world * radius
        radius -= center
        self.radius = radius
        self.center = bobj.parent.matrix_world.inverted() * center

    @classmethod
    def read(cls, bobj):
        for c in bobj.children:
            if c.name.startswith(cls.PREFIX):
                return cls(c)
        terminate("Occlusion not found in: ", bobj.name)

    def write(self):
        write_vector(self.radius)
        write_vector(self.center)


@Gearoenix.register
class Model(RenderObject):
    TYPE_DYNAMIC = 1
    TYPE_STATIC = 2
    TYPE_WIDGET = 3
    # TYPES OF WIDGET
    TYPE_BUTTON = 1
    TYPE_EDIT = 2
    TYPE_TEXT = 3

    @classmethod
    def init(cls):
        super().init()
        cls.DYNAMIC_PREFIX = cls.get_prefix() + 'dynamic-'
        cls.STATIC_PREFIX = cls.get_prefix() + 'static-'
        cls.WIDGET_PREFIX = cls.get_prefix() + 'widget-'
        cls.BUTTON_PREFIX = cls.WIDGET_PREFIX + 'button-'
        cls.EDIT_PREFIX = cls.WIDGET_PREFIX + 'edit-'
        cls.TEXT_PREFIX = cls.WIDGET_PREFIX + 'text-'

    def init_widget(self):
        if self.bobj.name.startswith(self.BUTTON_PREFIX):
            self.widget_type = self.TYPE_BUTTON
        elif self.bobj.name.startswith(self.TEXT_PREFIX):
            self.widget_type = self.TYPE_TEXT
        elif self.bobj.name.startswith(self.EDIT_PREFIX):
            self.widget_type = self.TYPE_EDIT
        else:
            terminate('Unrecognized widget type:', self.bobj.name)
        if self.widget_type == self.TYPE_EDIT or \
                self.widget_type == self.TYPE_TEXT:
            self.text = self.bobj.data.body.strip()
            self.font = Font.read(self.bobj.data.font)
            align_x = self.bobj.data.align_x
            align_y = self.bobj.data.align_y
            self.align = 0
            if align_x == 'LEFT':
                self.align += 3
            elif align_x == 'CENTER':
                self.align += 0
            elif align_x == 'RIGHT':
                self.align += 6
            else:
                terminate("Unrecognized text horizontal alignment, in:",
                          self.bobj.name)
            if align_y == 'TOP':
                self.align += 3
            elif align_y == 'CENTER':
                self.align += 2
            elif align_y == 'BOTTOM':
                self.align += 1
            else:
                terminate("Unrecognized text vertical alignment, in:",
                          self.bobj.name)
            self.font_shd = Shading(self.bobj.material_slots[0].material, self)
            self.font_space_character = self.bobj.data.space_character - 1.0
            self.font_space_word = self.bobj.data.space_word - 1.0
            self.font_space_line = self.bobj.data.space_line

    def __init__(self, bobj):
        super().__init__(bobj)
        self.matrix = bobj.matrix_world
        self.occlusion = Occlusion.read(bobj)
        self.meshes = []
        self.model_children = []
        self.collider = Collider.read(bobj)
        for c in bobj.children:
            ins = Mesh.read(c)
            if ins is not None:
                self.meshes.append(ins)
                continue
            ins = Gearoenix.Model.read(c)
            if ins is not None:
                self.model_children.append(ins)
                continue
        if len(self.model_children) + len(self.meshes) < 1 and \
                not bobj.name.startswith(self.TEXT_PREFIX):
            terminate('Waste model', bobj.name)
        if bobj.name.startswith(self.DYNAMIC_PREFIX):
            self.my_type = self.TYPE_DYNAMIC
        elif bobj.name.startswith(self.STATIC_PREFIX):
            self.my_type = self.TYPE_STATIC
        elif bobj.name.startswith(self.WIDGET_PREFIX):
            self.my_type = self.TYPE_WIDGET
            self.init_widget()
        else:
            terminate('Unspecified model type, in:', bobj.name)

    def write_widget(self):
        if self.widget_type == self.TYPE_TEXT or\
                self.widget_type == self.TYPE_EDIT:
            write_string(self.text)
            write_u8(self.align)
            write_float(self.font_space_character)
            write_float(self.font_space_word)
            write_float(self.font_space_line)
            write_u64(self.font.my_id)
            self.font_shd.write()

    def write(self):
        super().write()
        if self.my_type == self.TYPE_WIDGET:
            write_u64(self.widget_type)
        write_matrix(self.bobj.matrix_world)
        self.occlusion.write()
        self.collider.write()
        write_instances_ids(self.model_children)
        write_instances_ids(self.meshes)
        for mesh in self.meshes:
            mesh.shd.write()
        if self.my_type == self.TYPE_WIDGET:
            self.write_widget()


@Gearoenix.register
class Skybox(RenderObject):
    TYPE_BASIC = 1

    def __init__(self, bobj):
        super().__init__(bobj)
        self.my_type = 1
        self.mesh = None
        for c in bobj.children:
            if self.mesh is not None:
                terminate("Only one mesh is accepted.")
            self.mesh = Mesh.read(c)
            if self.mesh is None:
                terminate("Only one mesh is accepted.")
        self.mesh.shd = Shading(self.mesh.bobj.material_slots[0].material,
                                self)

    def write(self):
        super().write()
        write_u64(self.mesh.my_id)
        self.mesh.shd.write()


@Gearoenix.register
class Scene(RenderObject):
    TYPE_GAME = 1
    TYPE_UI = 2

    @classmethod
    def init(cls):
        super().init()
        cls.GAME_PREFIX = cls.get_prefix() + 'game-'
        cls.UI_PREFIX = cls.get_prefix() + 'ui-'

    def __init__(self, bobj):
        super().__init__(bobj)
        self.models = []
        self.skybox = None
        self.cameras = []
        self.lights = []
        self.audios = []
        self.constraints = []
        for o in bobj.objects:
            if o.parent is not None:
                continue
            ins = Gearoenix.Model.read(o)
            if ins is not None:
                self.models.append(ins)
                continue
            ins = Gearoenix.Skybox.read(o)
            if ins is not None:
                if self.skybox is not None:
                    terminate("Only one skybox is acceptable in a scene",
                              "wrong scene is: ", bobj.name)
                self.skybox = ins
                continue
            ins = Camera.read(o)
            if ins is not None:
                self.cameras.append(ins)
                continue
            ins = Light.read(o)
            if ins is not None:
                self.lights.append(ins)
                continue
            ins = Audio.read(o)
            if ins is not None:
                self.audios.append(ins)
                continue
            ins = Constraint.read(o)
            if ins is not None:
                self.constraints.append(ins)
                continue
        if bobj.name.startswith(self.GAME_PREFIX):
            self.my_type = self.TYPE_GAME
        elif bobj.name.startswith(self.UI_PREFIX):
            self.my_type = self.TYPE_UI
        else:
            terminate('Unspecified scene type, in:', bobj.name)
        if len(self.cameras) < 1:
            terminate('Scene must have at least one camera, in:', bobj.name)
        if len(self.lights) < 1:
            terminate('Scene must have at least one light, in:', bobj.name)
        self.boundary_left = None
        if 'left' in bobj:
            self.boundary_left = bobj['left']
            self.boundary_right = bobj['right']
            self.boundary_up = bobj['up']
            self.boundary_down = bobj['down']
            self.boundary_front = bobj['front']
            self.boundary_back = bobj['back']
            self.grid_x_count = int(bobj['x-grid-count'])
            self.grid_y_count = int(bobj['y-grid-count'])
            self.grid_z_count = int(bobj['z-grid-count'])

    def write(self):
        super().write()
        write_vector(self.bobj.world.ambient_color)
        write_instances_ids(self.cameras)
        write_instances_ids(self.audios)
        write_instances_ids(self.lights)
        write_instances_ids(self.models)
        write_bool(self.skybox is not None)
        if self.skybox is not None:
            write_u64(self.skybox.my_id)
        write_instances_ids(self.constraints)
        write_bool(self.boundary_left is not None)
        if self.boundary_left is not None:
            write_float(self.boundary_up)
            write_float(self.boundary_down)
            write_float(self.boundary_left)
            write_float(self.boundary_right)
            write_float(self.boundary_front)
            write_float(self.boundary_back)
            write_u16(self.grid_x_count)
            write_u16(self.grid_y_count)
            write_u16(self.grid_z_count)

    @classmethod
    def read_all(cls):
        for s in bpy.data.scenes:
            super().read(s)


@Gearoenix.register
def write_tables():
    Gearoenix.Shader.write_table()
    Gearoenix.Camera.write_table()
    Gearoenix.Audio.write_table()
    Gearoenix.Light.write_table()
    Gearoenix.Texture.write_table()
    Gearoenix.Font.write_table()
    Gearoenix.Mesh.write_table()
    Gearoenix.Model.write_table()
    Gearoenix.Skybox.write_table()
    Gearoenix.Constraint.write_table()
    Gearoenix.Scene.write_table()


@Gearoenix.register
def export_files():
    Gearoenix.initialize_pathes()
    Gearoenix.Audio.init()
    Gearoenix.Light.init()
    Gearoenix.Camera.init()
    Gearoenix.Texture.init()
    Gearoenix.Font.init()
    Gearoenix.Mesh.init()
    Gearoenix.Model.init()
    Gearoenix.Skybox.init()
    Gearoenix.Constraint.init()
    Gearoenix.Scene.init()
    Gearoenix.Scene.read_all()
    Gearoenix.write_bool(sys.byteorder == 'little')
    Gearoenix.tables_offset = file_tell()
    Gearoenix.write_tables()
    Gearoenix.Camera.write_all()
    Gearoenix.Audio.write_all()
    Gearoenix.Light.write_all()
    Gearoenix.Texture.write_all()
    Gearoenix.Font.write_all()
    Gearoenix.Mesh.write_all()
    Gearoenix.Model.write_all()
    Gearoenix.Skybox.write_all()
    Gearoenix.Constraint.write_all()
    Gearoenix.Scene.write_all()
    Gearoenix.GX3D_FILE.flush()
    Gearoenix.RUST_FILE.flush()
    Gearoenix.CPP_FILE.flush()
    Gearoenix.GX3D_FILE.seek(tables_offset)
    Gearoenix.RUST_FILE.seek(0)
    Gearoenix.CPP_FILE.seek(0)
    Gearoenix.write_tables()
    Gearoenix.GX3D_FILE.flush()
    Gearoenix.GX3D_FILE.close()
    Gearoenix.RUST_FILE.flush()
    Gearoenix.RUST_FILE.close()
    Gearoenix.CPP_FILE.flush()
    Gearoenix.CPP_FILE.close()


@Gearoenix.register
class Exporter(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """This is a plug in for Gearoenix 3D file format"""
    bl_idname = "gearoenix_exporter.data_structure"
    bl_label = "Export Gearoenix 3D"
    filename_ext = ".gx3d"
    filter_glob = bpy.props.StringProperty(
        default="*.gx3d",
        options={'HIDDEN'},
    )
    export_engine = bpy.props.EnumProperty(
        name="Game engine",
        description="This item select the game engine",
        items=(
            (str(Gearoenix.ENGINE_GEAROENIX), 'Gearoenix', ''),
            (str(Gearoenix.ENGINE_VULKUST), 'Vulkust', '')))

    def execute(self, context):
        engine = int(self.export_engine)
        if engine == Gearoenix.ENGINE_GEAROENIX:
            Gearoenix.EXPORT_GEAROENIX = True
            log_info("Exporting for Gearoenix engine")
        elif engine == Gearoenix.ENGINE_VULKUST:
            Gearoenix.EXPORT_VULKUST = True
            log_info("Exporting for Vulkust engine")
        else:
            terminate("Unexpected export engine")
        Gearoenix.EXPORT_FILE_PATH = self.filepath
        export_files()
        return {'FINISHED'}


@Gearoenix.register
def menu_func_export(self, context):
    self.layout.operator(
        Gearoenix.Exporter.bl_idname, text="Gearoenix 3D Exporter (.gx3d)")


@Gearoenix.register
def register_plugin():
    bpy.utils.register_class(Gearoenix.Exporter)
    bpy.types.INFO_MT_file_export.append(Gearoenix.menu_func_export)


if __name__ == "__main__":
    Gearoenix.register_plugin()
