bl_info = {
    "name": "Gearoenix Blender",
    "author": "Hossein Noroozpour",
    "version": (2, 0),
    "blender": (2, 7, 5),
    "api": 1,
    "location": "File > Export",
    "description": "Export several scene into a Gearoenix 3D file format.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export",
}

# The philosophy behind this plugin is to import everything that is engaged
#    at least in one of the blender scene in a file. Plan is not to take
#    everything from blender and support every features of Blender.
#    Always best practises are the correct way of presenting data.

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


class Gearoenix:
    TYPE_BOOLEAN = ctypes.c_uint8
    TYPE_OFFSET = ctypes.c_uint64
    TYPE_TYPE_ID = ctypes.c_uint64
    TYPE_SIZE = ctypes.c_uint64
    TYPE_COUNT = ctypes.c_uint64
    TYPE_BYTE = ctypes.c_uint8
    TYPE_FLOAT = ctypes.c_float
    TYPE_U32 = ctypes.c_uint32

    TEXTURE_TYPE_2D = 10
    TEXTURE_TYPE_CUBE = 20

    SPEAKER_TYPE_MUSIC = 10
    SPEAKER_TYPE_OBJECT = 20

    STRING_DYNAMIC_PART = 'dynamic-part'
    STRING_DYNAMIC_PARTED = 'dynamic-parted'
    STRING_CUTOFF = "cutoff"
    STRING_TRANSPARENT = "transparent"
    STRING_ENGINE_SDK_VAR_NAME = 'VULKUST_SDK'
    STRING_VULKAN_SDK_VAR_NAME = 'VULKAN_SDK'
    STRING_COPY_POSTFIX_FORMAT = '.NNN'
    STRING_2D_TEXTURE = '2d'
    STRING_3D_TEXTURE = '3d'
    STRING_CUBE_TEXTURE = 'cube'
    STRING_NRM_TEXTURE = 'normal'
    STRING_SPEC_TEXTURE = 'spectxt'
    STRING_BAKED_ENV_TEXTURE = 'baked' 
    STRING_CUBE_FACES = [
        "up", "down", "left", "right", "front", "back"
    ]

    PATH_ENGINE_SDK = None
    PATH_GEAROENIX_SDK = None
    PATH_SHADERS_DIR = None
    PATH_SHADER_COMPILER = None

    MODE_DEBUG = True

    class Shading:
        class Reserved(enum.Enum):
            WHITE_POS = 0
            WHITE_POS_NRM = 1
            WHITE_POS_UV = 2
            WHITE_POS_NRM_UV = 3
            MAX = 4

            def needs_normal(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def needs_uv(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def needs_tangent(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

        class Lighting(enum.Enum):
            RESERVED = 0
            SHADELESS = 1
            DIRECTIONAL = 2
            NORMALMAPPED = 3
            MAX = 4

            def needs_normal(self):
                if self == self.RESERVED:
                    raise Exception('I can not judge about reserved.')
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return self == self.DIRECTIONAL or self == self.NORMALMAPPED

            def needs_uv(self):
                if self == self.RESERVED:
                    raise Exception('I can not judge about reserved.')
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return self == self.NORMALMAPPED

            def needs_tangent(self):
                if self == self.RESERVED:
                    raise Exception('I can not judge about reserved.')
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return self == self.NORMALMAPPED

            def translate(self, gear, bmat, shd):
                found = 0
                nrm_txt = None
                for k in bmat.texture_slots.keys():
                    if k.endswith('-' + gear.STRING_NRM_TEXTURE):
                        found += 1
                        nrm_txt = bmat.texture_slots[k].texture
                normal_found = False
                if found == 1:
                    normal = True
                else:
                    gear.show("Two normal found for material" + bmat.name)
                shadeless = bmat.use_shadeless:
                if shadeless and normal_found:
                    gear.show("One material can not have both normal-map texture and have a shadeless lighting, error found in material: " + bmat.name)
                if shadeless:
                    return self.SHADELESS
                if not normal_found:
                    return self.DIRECTIONAL
                shd.normalmap = gear.read_texture_2d(nrm_txt)
                return self.NORMALMAPPED

        class Texturing(enum.Enum):
            COLORED = 0
            D2 = 1
            D3 = 2
            CUBE = 3
            MAX = 4

            def needs_normal(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def needs_uv(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return self == self.D2

            def needs_tangent(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def translate(self, gear, bmat, shd):
                d2_found = 0
                d2txt = None
                d3_found = 0
                d3txt = None
                cube_found = [0 for i in range(6)]
                cubetxt = None
                for k in bmat.texture_slots.keys():
                    if k.endswith('-' + gear.STRING_2D_TEXTURE):
                        d2_found += 1
                        d2txt = bmat.texture_slots[k].texture
                    elif k.endswith('-' + gear.STRING_3D_TEXTURE):
                        d3_found += 1
                        d3txt = bmat.texture_slots[k].texture
                    else:
                        for i in range(6):
                            stxt = '-' + gear.STRING_CUBE_TEXTURE + '-' + gear.STRING_CUBE_FACES[i]
                            if k.endswith(stxt):
                                cube_found[i] += 1
                                cubetxt = stxt[:len(k)-len(stxt)] + '-' + gear.STRING_CUBE_TEXTURE
                if d2_found > 1:
                    gear.show("Number of 2D texture is more than 1 in material: " + bmat.name)
                d2_found = d2_found == 1
                if d3_found > 1:
                    gear.show("Number of 3D texture is more than 1 in material: " + bmat.name)
                d3_found = d3_found == 1
                for i in range(6):
                    if cube_found[i] > 1:
                        gear.show("Number of " + gear.STRING_CUBE_FACES[i] + " face for cube texture is more than 1 in material: " + bmat.name)
                    cube_found[i] = cube_found[i] == 1
                for i in range(1, 6):
                    if cube_found[0] != cube_found[i]:
                        gear.show("Incomplete cube texture in material: " + bmat.name)
                cube_found = cube_found[0]
                found = 0
                if d2_found:
                    found += 1
                if d3_found:
                    found += 1
                if cube_found:
                    found += 1
                if found == 0:
                    return self.COLORED
                if found > 1:
                    gear.show("Each material only can have one of 2D, 3D or Cube textures, Error in material: ", bmat.name)
                if d2_found:
                    shd.d2 = gear.read_texture_2d(d2txt)
                    return self.D2
                if d3_found:
                    shd.d3 = gear.read_texture_3d(d3txt)
                    return self.D3
                if cube_found:
                    shd.cube = gear.read_texture_cube(bmat.texture_slots, cubetxt)
                    return self.CUBE



        class Speculating(enum.Enum):
            MATTE = 0
            SPECULATED = 1
            SPECTXT = 2
            MAX = 3

            def needs_normal(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return self != self.MATTE

            def needs_uv(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return self == self.SPECTXT

            def needs_tangent(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def translate(self, gear, bmat, shd):
                found = 0
                txt = None
                for k in bmat.texture_slots.keys():
                    if k.endswith('-' + gear.STRING_SPEC_TEXTURE):
                        found += 1
                        txt = bmat.texture_slots[k].texture
                if found > 1:
                    gear.show("Each material only can have one secular texture, Error in material: ", bmat.name)
                if found == 1:
                    shd.spectxt = gear.read_texture_2d(txt)
                    return self.SPECTXT
                if bmat.specular_intensity > 0.01:
                    return self.SPECULATED
                return self.MATTE

        class EnvironmentMapping(enum.Enum):
            NONREFLECTIVE = 0
            BAKED = 1
            REALTIME = 2
            MAX = 3

            def needs_normal(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return self != self.NONREFLECTIVE

            def needs_uv(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def needs_tangent(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def translate(self, gear, bmat, shd):
                baked_found = [0 for i in range(6)]
                bakedtxt = None
                for k in bmat.texture_slots.keys():
                    for i in range(6):
                        stxt = '-' + gear.STRING_BAKED_ENV_TEXTURE + '-' + gear.STRING_CUBE_FACES[i]
                        if k.endswith(stxt):
                            baked_found[i] += 1
                            bakedtxt = stxt[:len(k)-len(stxt)] + '-' + gear.STRING_BAKED_ENV_TEXTURE
                for i in range(6):
                    if baked_found[i] > 1:
                        gear.show("Number of " + gear.STRING_CUBE_FACES[i] + " face for baked texture is more than 1 in material: " + bmat.name)
                    baked_found[i] = baked_found[i] == 1
                    if baked_found[0] != baked_found[i]:
                        gear.show("Incomplete cube texture in material: " + bmat.name)
                baked_found = baked_found[0]
                reflective = bmat.raytrace_mirror is not None and bmat.raytrace_mirror.use and bmat.raytrace_mirror.reflect_factor > 0.001
                if baked_found and not reflective:
                    gear.show("A material must set amount of reflectivity and then have a baked-env texture. Error in material: " + bmat.name)
                if baked_found:
                    shd.bakedenv = gear.read_texture_cube(bmat.texture_slots, bakedtxt)
                    return self.BAKED
                if reflective:
                    return self.REALTIME
                return self.NONREFLECTIVE

        class Shadowing(enum.Enum):
            SHADOWLESS = 0
            CASTER = 1
            FULL = 2
            MAX = 3

            def needs_normal(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return self == self.FULL

            def needs_uv(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def needs_tangent(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def translate(self, gear, bmat, shd):
                caster = bmat.use_cast_shadows
                receiver = bmat.use_receive
                if not caster and receiver:
                    gear.show("A material can not be receiver but not caster. Error in material: " + bmat.name)
                if not caster:
                    return self.SHADOWLESS
                if receiver:
                    return self.FULL
                return self.CASTER

        class Transparency(enum.Enum):
            OPAQUE = 1
            TRANSPARENT = 2
            CUTOFF = 3
            MAX = 4

            def needs_normal(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def needs_uv(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return self == self.CUTOFF

            def needs_tangent(self):
                if self == self.MAX:
                    raise Exception('UNEXPECTED')
                return False

            def translate(self, gear, bmat, shd):
                trn = gear.STRING_TRANSPARENT in bmat
                ctf = gear.STRING_CUTOFF in bmat
                if trn and ctf:
                    gear.show("A material can not be transparent and cutoff in same time. Error in material: " + bmat.name)
                if trn:
                    return self.TRANSPARENT
                if ctf:
                    return self.CUTOFF
                return OPAQUE

        def __init__(self, parent, bmat=None):
            self.parent = parent
            self.shading_data = [
                self.Lighting.SHADELESS,
                self.Texturing.COLORED,
                self.Speculating.MATTE,
                self.EnvironmentMapping.NONREFLECTIVE,
                self.Shadowing.SHADOWLESS,
                self.Transparency.OPAQUE,
            ]
            self.reserved = self.Reserved.WHITE_POS
            self.normalmap = None
            self.d2 = None
            self.d3 = None
            self.cube = None
            self.spectxt = None
            self.bakedenv = None
            self.bmat = bmat
            if bmat is not None:
                for i in range(len(self.shading_data)):
                    self.shading_data[i] = self.shading_data[i].translate(parent, bmat, shd)


        def set_lighting(self, e):
            if not isinstance(e, self.Lighting) or e.MAX == e:
                self.parent.show("Unexpected ", e)
            self.shading_data[0] = e

        def get_lighting(self):
            if self.is_reserved():
                return self.Lighting.MAX
            return self.shading_data[0]

        def set_texturing(self, e):
            if not isinstance(e, self.Texturing) or e.MAX == e:
                self.parent.show("Unexpected ", e)
            self.shading_data[1] = e

        def get_texturing(self):
            if self.is_reserved():
                return self.Texturing.MAX
            return self.shading_data[1]

        def set_speculating(self, e):
            if not isinstance(e, self.Speculating) or e.MAX == e:
                self.parent.show("Unexpected ", e)
            self.shading_data[2] = e

        def get_speculating(self):
            if self.is_reserved():
                return self.Speculating.MAX
            return self.shading_data[2]

        def set_environment_mapping(self, e):
            if not isinstance(e, self.EnvironmentMapping) or e.MAX == e:
                self.parent.show("Unexpected ", e)
            self.shading_data[3] = e

        def get_environment_mapping(self):
            if self.is_reserved():
                return self.EnvironmentMapping.MAX
            return self.shading_data[3]

        def set_shadowing(self, e):
            if not isinstance(e, self.Shadowing) or e.MAX == e:
                self.parent.show("Unexpected ", e)
            self.shading_data[4] = e

        def get_shadowing(self):
            if self.is_reserved():
                return self.Shadowing.MAX
            return self.shading_data[4]

        def set_transparency(self, e):
            if not isinstance(e, self.Transparency) or e.MAX == e:
                self.parent.show("Unexpected ", e)
            self.shading_data[5] = e

        def get_transparency(self):
            if self.is_reserved():
                return self.Transparency.MAX
            return self.shading_data[5]

        def set_reserved(self, e):
            if not isinstance(e, self.Reserved) or e.MAX == e:
                self.parent.show("Unexpected ", e)
            self.shading_data[0] = self.Lighting.RESERVED
            self.reserved = e

        def is_reserved(self):
            return self.shading_data[0] == self.Lighting.RESERVED

        def to_int(self):
            if self.is_reserved():
                return int(self.reserved.value)
            result = int(self.Reserved.MAX.value)
            coef = int(1)
            for e in self.shading_data:
                result += int(e.value) * coef
                coef *= int(e.MAX.value)
            return result

        def print_all_enums(self):
            all_enums = dict()

            def sub_print(es, pre, shd):
                if len(es) == 0:
                    shd.shading_data = pre
                    # print(pre)
                    all_enums[shd.get_enum_name()] = shd.to_int()
                else:
                    for e in es[0]:
                        sub_print(es[1:], pre + [e], shd)
            sub_print([
                self.Lighting,
                self.Texturing,
                self.Speculating,
                self.EnvironmentMapping,
                self.Shadowing,
                self.Transparency], [], self)
            self.shading_data[0] = self.Lighting.RESERVED
            for e in self.Reserved:
                self.reserved = e
                all_enums[self.get_enum_name()] = self.to_int()
            self.parent.log("ALL ENUMS")
            for k in sorted(all_enums):
                if 'MAX' not in k:
                    self.parent.log(k, "=", all_enums[k], ",")
            self.parent.log("END OF ALL ENUMS")

        def get_enum_name(self):
            result = ""
            if self.is_reserved():
                result = self.reserved.name + '_'
            else:
                for e in self.shading_data:
                    result += e.name + '_'
            result = result[0:len(result) - 1]
            self.parent.log(result, ' = ', self.to_int())
            return result

        def get_file_name(self):
            result = self.get_enum_name()
            result = result.lower().replace('_', '-')
            self.parent.log(result, ' = ', self.to_int())
            return result

        def needs_normal(self):
            if self.is_reserved():
                return self.reserved.needs_normal()
            for e in self.shading_data:
                if e.needs_normal():
                    return True
            return False

        def needs_uv(self):
            if self.is_reserved():
                return self.reserved.needs_uv()
            for e in self.shading_data:
                if e.needs_uv():
                    return True
            return False

        def needs_tangent(self):
            if self.is_reserved():
                return self.reserved.needs_tangent()
            for e in self.shading_data:
                if e.needs_tangent():
                    return True
            return False

    def __init__(self):
        pass

    class ErrorMsgBox(bpy.types.Operator):
        bl_idname = "gearoenix_exporter.message_box"
        bl_label = "Error"
        gearoenix_exporter_msg = 'Unknown Error!'

        def execute(self, context):
            self.report({'ERROR'},
                        Gearoenix.ErrorMsgBox.gearoenix_exporter_msg)
            return {'CANCELLED'}

    @classmethod
    def log(cls, *args):
        if cls.MODE_DEBUG:
            print(*args)

    @classmethod
    def show(cls, msg):
        cls.ErrorMsgBox.gearoenix_exporter_msg = msg
        bpy.ops.gearoenix_exporter.message_box()
        raise Exception(error)

    @classmethod
    def check_env(cls):
        cls.PATH_ENGINE_SDK = os.environ.get(cls.STRING_ENGINE_SDK_VAR_NAME)
        if cls.PATH_ENGINE_SDK is None:
            cls.show('"' + cls.STRING_ENGINE_SDK_VAR_NAME +
                     '" variable is not set!')
            return False
        cls.PATH_SHADERS_DIR = cls.PATH_ENGINE_SDK + '/vulkust/src/shaders/'
        if sys.platform == 'darwin':
            cls.PATH_SHADER_COMPILER = "xcrun"
        else:
            cls.PATH_VULKAN_SDK = os.environ.get(
                cls.STRING_VULKAN_SDK_VAR_NAME)
            if cls.PATH_VULKAN_SDK is None:
                cls.show('"' + cls.STRING_VULKAN_SDK_VAR_NAME +
                         '" variable is not set!')
                return False
            cls.PATH_SHADER_COMPILER = \
                cls.PATH_VULKAN_SDK + '/bin/glslangValidator'
        return True

    @classmethod
    def compile_shader(cls, stage, shader_name):
        tmp = cls.TmpFile()
        args = None
        if sys.platform == 'darwin':
            args = [
                cls.PATH_SHADER_COMPILER, '-sdk', 'macosx', 'metal',
                shader_name, '-o', tmp.filename
            ]
        else:
            args = [
                cls.PATH_SHADER_COMPILER, '-V', '-S', stage, shader_name, '-o',
                tmp.filename
            ]
        if subprocess.run(args).returncode != 0:
            cls.show('Shader %s can not be compiled!' % shader_name)
        if sys.platform == "darwin":
            tmp2 = tmp
            tmp = cls.TmpFile()
            args = [
                cls.PATH_SHADER_COMPILER, '-sdk', 'macosx', 'metallib',
                tmp2.filename, '-o', tmp.filename
            ]
            if subprocess.run(args).returncode != 0:
                cls.show('Shader %s can not be build!' % shader_name)
        tmp = tmp.read()
        cls.log("Shader '", shader_name,
                "'is compiled has length of: ", len(tmp))
        cls.out.write(cls.TYPE_SIZE(len(tmp)))
        cls.out.write(tmp)

    @staticmethod
    def const_string(s):
        return s.replace("-", "_").upper()

    @classmethod
    def write_bool(cls, b):
        data = 0
        if b:
            data = 1
        cls.out.write(cls.TYPE_BOOLEAN(data))

    @classmethod
    def write_vector(cls, v, element_count=3):
        for i in range(element_count):
            cls.out.write(cls.TYPE_FLOAT(v[i]))

    @classmethod
    def write_matrix(cls, matrix):
        for i in range(0, 4):
            for j in range(0, 4):
                cls.out.write(cls.TYPE_FLOAT(matrix[j][i]))

    @classmethod
    def write_offset_array(cls, arr):
        cls.out.write(cls.TYPE_COUNT(len(arr)))
        for o in arr:
            cls.out.write(cls.TYPE_OFFSET(o))

    @classmethod
    def write_shaders_table(cls):
        cls.out.write(cls.TYPE_COUNT(len(cls.shaders)))
        for shader_id, offset_obj in cls.shaders.items():
            offset, obj = offset_obj
            cls.out.write(cls.TYPE_TYPE_ID(shader_id))
            cls.out.write(cls.TYPE_OFFSET(offset))
            cls.log("Shader with id:", shader_id, "and offset:", offset)

    @classmethod
    def items_offsets(cls, items, mod_name):
        offsets = [i for i in range(len(items))]
        cls.rust_code.write("pub mod " + mod_name + " {\n")
        for name, offset_id in items.items():
            offset, item_id = offset_id[0:2]
            cls.rust_code.write("\tpub const " + cls.const_string(name) +
                                ": u64 = " + str(item_id) + ";\n")
            offsets[item_id] = offset
        cls.rust_code.write("}\n")
        return offsets

    @classmethod
    def gather_cameras_offsets(cls):
        cls.cameras_offsets = cls.items_offsets(cls.cameras, "camera")

    @classmethod
    def gather_speakers_offsets(cls):
        cls.speakers_offsets = cls.items_offsets(cls.speakers, "speaker")

    @classmethod
    def gather_lights_offsets(cls):
        cls.lights_offsets = cls.items_offsets(cls.lights, "light")

    @classmethod
    def gather_textures_offsets(cls):
        cls.textures_offsets = cls.items_offsets(cls.textures, "texture")

    @classmethod
    def gather_models_offsets(cls):
        cls.models_offsets = cls.items_offsets(cls.models, "model")

    @classmethod
    def gather_scenes_offsets(cls):
        cls.scenes_offsets = cls.items_offsets(cls.scenes, "scene")

    @classmethod
    def write_shaders(cls):
        for shader_id in cls.shaders.keys():
            file_name = cls.shaders[shader_id][1].get_file_name()
            cls.shaders[shader_id][0] = cls.out.tell()
            if cls.export_metal:
                cls.show("TODO implementation changed")
                file_name = 'metal/' + file_name + '-%s.metal'
                file_name = cls.PATH_SHADERS_DIR + file_name
                cls.compile_shader('vert', file_name % 'vert')
                cls.compile_shader('frag', file_name % 'frag')
            elif cls.export_vulkan:
                cls.show("TODO implementation changed")
                file_name = 'vulkan/' + file_name + '.%s'
                file_name = cls.PATH_SHADERS_DIR + file_name
                cls.compile_shader('vert', file_name % 'vert')
                cls.compile_shader('frag', file_name % 'frag')

    @classmethod
    def write_cameras(cls):
        items = [i for i in range(len(cls.cameras))]
        for name, offset_id in cls.cameras.items():
            offset, iid = offset_id
            items[iid] = name
        for name in items:
            obj = bpy.data.objects[name]
            cam = obj.data
            cls.cameras[name][0] = cls.out.tell()
            if cam.type == 'PERSP':
                cls.out.write(cls.TYPE_TYPE_ID(1))
            else:
                cls.show("Camera with type '" + cam.type +
                         "' is not supported yet.")
            cls.out.write(cls.TYPE_FLOAT(obj.location[0]))
            cls.out.write(cls.TYPE_FLOAT(obj.location[1]))
            cls.out.write(cls.TYPE_FLOAT(obj.location[2]))
            cls.out.write(cls.TYPE_FLOAT(obj.rotation_euler[0]))
            cls.out.write(cls.TYPE_FLOAT(obj.rotation_euler[1]))
            cls.out.write(cls.TYPE_FLOAT(obj.rotation_euler[2]))
            cls.out.write(cls.TYPE_FLOAT(cam.clip_start))
            cls.out.write(cls.TYPE_FLOAT(cam.clip_end))
            cls.out.write(cls.TYPE_FLOAT(cam.angle_x / 2.0))

    @classmethod
    def write_speakers(cls):
        items = [i for i in range(len(cls.speakers))]
        for name, offset_id in cls.speakers.items():
            offset, iid, ttype = offset_id_type
            items[iid] = (name, ttype)
        for name, ttype in items:
            cls.speakers[name][0] = cls.out.tell()
            cls.out.write(cls.TYPE_TYPE_ID(ttype))
            cls.write_binary_file(name)

    @classmethod
    def write_lights(cls):
        items = [i for i in range(len(cls.lights))]
        for name, offset_id in cls.lights.items():
            offset, iid = offset_id
            items[iid] = name
        for name in items:
            sun = bpy.data.objects[name]
            cls.lights[name][0] = cls.out.tell()
            # This is temporary, only for keeping the design
            cls.out.write(cls.TYPE_TYPE_ID(10))
            cls.out.write(cls.TYPE_FLOAT(sun.location[0]))
            cls.out.write(cls.TYPE_FLOAT(sun.location[1]))
            cls.out.write(cls.TYPE_FLOAT(sun.location[2]))
            cls.out.write(cls.TYPE_FLOAT(sun.rotation_euler[0]))
            cls.out.write(cls.TYPE_FLOAT(sun.rotation_euler[1]))
            cls.out.write(cls.TYPE_FLOAT(sun.rotation_euler[2]))
            cls.out.write(cls.TYPE_FLOAT(sun['near']))
            cls.out.write(cls.TYPE_FLOAT(sun['far']))
            cls.out.write(cls.TYPE_FLOAT(sun['size']))
            cls.write_vector(sun.data.color)

    @classmethod
    def write_binary_file(cls, name):
        f = open(name, "rb")
        f = f.read()
        cls.out.write(cls.TYPE_COUNT(len(f)))
        cls.out.write(f)

    @classmethod
    def write_textures(cls):
        items = [i for i in range(len(cls.textures))]
        for name, offset_id_type in cls.textures.items():
            offset, iid, ttype = offset_id_type
            items[iid] = [name, ttype]
        for name, ttype in items:
            cls.textures[name][0] = cls.out.tell()
            cls.out.write(cls.TYPE_TYPE_ID(ttype))
            if ttype == cls.TEXTURE_TYPE_2D:
                cls.log("txt2-----------------------", cls.out.tell())
                cls.write_binary_file(name)
            elif ttype == cls.TEXTURE_TYPE_CUBE:
                name = name.strip()
                raw_name = name[:len(name) - len("-up.png")]
                cls.write_binary_file(raw_name + "-up.png")
                cls.write_binary_file(raw_name + "-down.png")
                cls.write_binary_file(raw_name + "-left.png")
                cls.write_binary_file(raw_name + "-right.png")
                cls.write_binary_file(raw_name + "-front.png")
                cls.write_binary_file(raw_name + "-back.png")
            else:
                cls.show("Unexpected texture type:", ttype)

    @staticmethod
    def check_uint(s):
        try:
            if int(s) >= 0:
                return True
        except ValueError:
            return False
        return False

    @classmethod
    def assert_copied_model(cls, name):
        psf = cls.STRING_COPY_POSTFIX_FORMAT
        lpsf = len(psf)
        ln = len(name)
        if ln > lpsf and name[ln - lpsf] == psf[0] and \
                cls.check_uint(name[ln - (lpsf - 1):]):
            origin = name[:ln - lpsf]
            origin = bpy.data.objects[origin]
            if origin.parent is not None:
                cls.show("Object " + origin + " must be root because it is " +
                         "copied in " + name)
            if origin.matrix_world != mathutils.Matrix():
                cls.show("Object " + origin + " must not have any " +
                         "transformation because it is copied in " + name)
            if cls.STRING_DYNAMIC_PARTED in origin:
                cls.show("Object " + origin.name +
                         "must not have any dynamic part.")
            return origin
        return None

    @classmethod
    def assert_model_name(cls, name):
        # this is True for now but in future it may change
        pass

    @classmethod
    def material_needs_normal(cls, shd):
        shading = cls.shaders[shd][1]
        return shading.needs_normal()

    @classmethod
    def material_needs_uv(cls, shd):
        shading = cls.shaders[shd][1]
        return shading.needs_uv()

    @classmethod
    def write_material_texture_ids(cls, obj, shd):
        shading = cls.shaders[shd][1]
        if shading.get_texturing() != cls.Shading.Texturing.TEXTURED and \
            shading.get_environment_mapping() != \
                cls.Shading.EnvironmentMapping.BAKED:
            return
        cube_texture = None
        texture_2d = None
        materials_count = len(obj.material_slots.keys())
        has_cube = materials_count > len(cls.STRING_CUBE_TEXTURE_FACES)
        if has_cube:
            for mat in obj.material_slots.keys():
                m = obj.material_slots[mat].material
                if has_cube and m.name.endswith(
                        "-" + cls.STRING_CUBE_TEXTURE_FACES[0]):
                    name = bpy.path.abspath(
                        m.texture_slots[0].texture.image.filepath_raw)
                    cube_texture = cls.textures[name][1]
                    continue
                sm = m.name.split("-")
                if ("-" not in m.name) or len(sm) < 2 or \
                        (sm[len(sm) - 1] not in cls.STRING_CUBE_TEXTURE_FACES):
                    if cls.has_material_texture2d(m):
                        name = bpy.path.abspath(
                            m.texture_slots[0].texture.image.filepath_raw)
                        texture_2d = cls.textures[name][1]
                    continue
        else:
            m = obj.material_slots[0].material
            n = bpy.path.abspath(m.texture_slots[0].texture.image.filepath_raw)
            texture_2d = cls.textures[n][1]
        if cube_texture is not None:
            cls.out.write(cls.TYPE_TYPE_ID(cube_texture))
        if texture_2d is not None:
            cls.out.write(cls.TYPE_TYPE_ID(texture_2d))

    @classmethod
    def get_info_material(cls, obj):
        slots = obj.material_slots
        materials_count = len(slots.keys())
        if materials_count == 1:
            return slots[0].material
        for mat in slots.keys():
            m = slots[mat].material
            sm = m.name.split("-")
            if ("-" not in m.name) or len(sm) < 2 or \
                    (sm[len(sm) - 1] not in cls.STRING_CUBE_TEXTURE_FACES):
                return m

    @classmethod
    def get_up_face_material(cls, obj):
        slots = obj.material_slots
        materials_count = len(slots.keys())
        if materials_count < len(cls.STRING_CUBE_TEXTURE_FACES):
            return None
        for mat in slots.keys():
            m = slots[mat].material
            if m.name.endswith("-" + cls.STRING_CUBE_TEXTURE_FACES[0]):
                return m

    @classmethod
    def write_material_data(cls, obj, shd):
        cls.out.write(cls.TYPE_TYPE_ID(shd))
        cls.write_material_texture_ids(obj, shd)
        shading = cls.shaders[shd][1]
        if shading.is_reserved():
            return
        if shading.get_texturing() == cls.Shading.Texturing.COLORED:
            cls.write_vector(cls.get_info_material(obj).diffuse_color)
        if shading.get_speculating() == cls.Shading.Speculating.SPECULATED:
            cls.write_vector(cls.get_info_material(obj).specular_color)
            cls.out.write(
                cls.TYPE_FLOAT(cls.get_info_material(obj).specular_intensity))
        if shading.get_environment_mapping() != \
                cls.Shading.EnvironmentMapping.NONREFLECTIVE:
            cls.out.write(
                cls.TYPE_FLOAT(
                    cls.get_up_face_material(obj)
                    .raytrace_mirror.reflect_factor))
        transparency = shading.get_transparency()
        if transparency == cls.Shading.Transparency.TRANSPARENT:
            info = cls.get_info_material(obj)
            cls.out.write(cls.TYPE_FLOAT(info[cls.STRING_TRANSPARENT]))
        elif transparency == cls.Shading.Transparency.CUTOFF:
            info = cls.get_info_material(obj)
            cls.out.write(cls.TYPE_FLOAT(info[cls.STRING_CUTOFF]))

    @classmethod
    def write_mesh(cls, obj, shd, matrix):
        cls.log("before material: ", cls.out.tell())
        cls.write_material_data(obj, shd)
        cls.log("after material: ", cls.out.tell())
        msh = obj.data
        nrm = cls.material_needs_normal(shd)
        uv = cls.material_needs_uv(shd)
        vertices = dict()
        last_index = 0
        for p in msh.polygons:
            if len(p.vertices) > 3:
                cls.show("Object " + obj.name + " is not triangled!")
            for i, li in zip(p.vertices, p.loop_indices):
                vertex = []
                v = matrix * msh.vertices[i].co
                vertex.append(v[0])
                vertex.append(v[1])
                vertex.append(v[2])
                if nrm:
                    normal = msh.vertices[i].normal
                    normal = mathutils.Vector(
                        (normal[0], normal[1], normal[2], 0.0))
                    normal = matrix * normal
                    normal = normal.normalized()
                    vertex.append(normal[0])
                    vertex.append(normal[1])
                    vertex.append(normal[2])
                if uv:
                    uv_lyrs = msh.uv_layers
                    if len(uv_lyrs) > 1 or len(uv_lyrs) < 1:
                        cls.show("Unexpected number of uv layers in " +
                                 obj.name)
                    texco = uv_lyrs.active.data[li].uv
                    vertex.append(texco[0])
                    vertex.append(texco[1])
                vertex = tuple(vertex)
                if vertex in vertices:
                    vertices[vertex].append(last_index)
                else:
                    vertices[vertex] = [last_index]
                last_index += 1
        indices = [0 for _ in range(last_index)]
        last_index = 0
        cls.out.write(cls.TYPE_COUNT(len(vertices)))
        for vertex, index_list in vertices.items():
            for e in vertex:
                cls.out.write(cls.TYPE_FLOAT(e))
            for i in index_list:
                indices[i] = last_index
            last_index += 1
        cls.out.write(cls.TYPE_COUNT(len(indices)))
        for i in indices:
            cls.out.write(cls.TYPE_U32(i))

    @staticmethod
    def model_has_dynamic_parent(obj):
        o = obj.parent
        while o is not None:
            if cls.STRING_DYNAMIC_PART in o:
                return True
            o = o.parent
        return False

    @classmethod
    def write_model(cls, name, inv_mat_par=mathutils.Matrix()):
        obj = bpy.data.objects[name]
        dyn = cls.STRING_DYNAMIC_PART in obj
        origin = cls.assert_copied_model(name)
        is_copy = origin is not None
        cls.write_bool(is_copy)
        if is_copy:
            cls.write_matrix(obj.matrix_world)
            cls.out.write(cls.TYPE_TYPE_ID(cls.models[origin.name][1]))
            return
        cls.write_bool(dyn)
        mesh_matrix = mathutils.Matrix()
        child_inv = inv_mat_par
        if dyn:
            cls.write_matrix(obj.matrix_world)
            child_inv = obj.matrix_world.inverted()
        else:
            mesh_matrix = inv_mat_par * obj.matrix_world
        shd = cls.get_shader_id(obj)
        if obj.parent is None or dyn:
            if len(obj.children) == 0:
                cls.show("Object " + obj.name + " should not have zero " +
                         "children count")
        cls.write_mesh(obj, shd, child_inv)
        cls.out.write(cls.TYPE_COUNT(len(obj.children)))
        for c in obj.children:
            cls.write_model(c.name, child_inv)

    @classmethod
    def write_models(cls):
        items = [i for i in range(len(cls.models))]
        for name, (offset, iid) in cls.models.items():
            items[iid] = name
        for name in items:
            cls.assert_model_name(name)
            cls.models[name][0] = cls.out.tell()
            cls.log("model with name:", name,
                    " and offset:", cls.models[name][0])
            cls.write_model(name)

    @classmethod
    def write_scenes(cls):
        items = [i for i in range(len(cls.scenes))]
        for name, offset_id in cls.scenes.items():
            offset, iid = offset_id
            items[iid] = name
        for name in items:
            cls.scenes[name][0] = cls.out.tell()
            cls.log("offset of scene with name",
                    name, ":", cls.scenes[name][0])
            scene = bpy.data.scenes[name]
            models = []
            cameras = []
            speakers = []
            lights = []
            for o in scene.objects:
                if o.parent is not None:
                    continue
                if o.type == "MESH":
                    models.append(cls.models[o.name][1])
                elif o.type == "CAMERA":
                    cameras.append(cls.cameras[o.name][1])
                elif o.type == "SPEAKER":
                    speakers.append(cls.speakers[o.name][1])
                elif o.type == "LAMP":
                    lights.append(cls.lights[o.name][1])
            if len(lights) > 1:
                cls.show(
                    "Currently only one light is supported in game engine")
            if len(cameras) < 1:
                cls.show("At least one camera must exist.")
            cls.out.write(cls.TYPE_COUNT(len(cameras)))
            for c in cameras:
                cls.out.write(cls.TYPE_TYPE_ID(c))
            cls.out.write(cls.TYPE_COUNT(len(speakers)))
            for s in speakers:
                cls.out.write(cls.TYPE_TYPE_ID(s))
            cls.out.write(cls.TYPE_COUNT(len(lights)))
            for l in lights:
                cls.out.write(cls.TYPE_TYPE_ID(l))
            cls.out.write(cls.TYPE_COUNT(len(models)))
            for m in models:
                cls.out.write(cls.TYPE_TYPE_ID(m))
            cls.write_vector(scene.world.ambient_color, 3)

    @classmethod
    def model_has_dynamic_part(cls, m):
        has_dynamic_child = cls.STRING_DYNAMIC_PART in m and \
            m[cls.STRING_DYNAMIC_PART] == 1.0
        for c in m.children:
            has_dynamic_child = \
                has_dynamic_child or cls.model_has_dynamic_part(c)
        return has_dynamic_child

    @classmethod
    def assert_model_dynamism(cls, m):
        for c in m.children:
            cls.assert_model_dynamism(c)
        d = cls.model_has_dynamic_part(m)
        if cls.STRING_DYNAMIC_PARTED in m and \
                m[cls.STRING_DYNAMIC_PARTED] == 1.0:
            if d:
                return
            else:
                cls.show("Model: " + m.name + " has " + cls.
                         STRING_DYNAMIC_PARTED + " property but does not have "
                         + " a correct " + cls.STRING_DYNAMIC_PART + " child.")
        else:
            if d:
                cls.show("Model: " + m.name + " does not have a correct " +
                         cls.STRING_DYNAMIC_PARTED +
                         " property but has a correct " +
                         cls.STRING_DYNAMIC_PART + " child.")
            else:
                return

    @classmethod
    def read_texture(cls, t) -> str:
        """It checks the correctness of a texture and returns its file path."""
        if t.type != 'IMAGE':
            cls.show("Only image textures is supported, please correct: " + t.name)
        img = t.image
        if img is None:
            cls.show("Image is not set in texture: " + t.name)
        filepath = bpy.path.abspath(img.filepath_raw).strip()
        if filepath is None or len(filepath) == 0:
            cls.show("Image is not specified yet in texture: " + t.name)
        if not filepath.endswith(".png"):
            cls.show("Use PNG image instead of " + filepath)
        return filepath


    @classmethod
    def read_texture_cube(cls, slots, tname) -> int:
        """It checks the correctness of a 2d texture and add its up face to the textures and returns id"""
        t = slots[tname + '-' + cls.STRING_CUBE_FACES[0]].texture
        filepath = cls.read_texture(t)
        for i in range(1, 6):
            cls.read_texture(slots[tname + '-' + cls.STRING_CUBE_FACES[i]].texture)
        if filepath in cls.textures:
            if cls.textures[filepath][2] != cls.TEXTURE_TYPE_CUBE:
                cls.show("You have used a same image in two defferent texture type in " + t.name)
            else:
                return cls.textures[filepath][1]
        else:
            cls.textures[filepath] = [0, cls.last_texture_id, cls.TEXTURE_TYPE_CUBE]
            tid = cls.last_texture_id
            cls.last_texture_id += 1
            return tid

    @classmethod
    def read_texture_2d(cls, t) -> int:
        """It checks the correctness of a 2d texture and add it to the textures and returns id"""
        filepath = read_texture(t)
        if filepath in cls.textures:
            if cls.textures[filepath][2] != cls.TEXTURE_TYPE_2D:
                cls.show("You have used a same image in two defferent " +
                         "texture type in " + t.name)
            else:
                return cls.textures[filepath][1]
        else:
            cls.textures[filepath] = \
                [0, cls.last_texture_id, cls.TEXTURE_TYPE_2D]
            tid = cls.last_texture_id
            cls.last_texture_id += 1
            return tid

    @classmethod
    def read_material(cls, m, environment=Shading.EnvironmentMapping.NONREFLECTIVE):
        s = cls.Shading(cls)
        s.set_environment_mapping(environment)
        if m.use_shadeless:
            s.set_lighting(cls.Shading.Lighting.SHADELESS)
        else:
            s.set_lighting(cls.Shading.Lighting.DIRECTIONAL)
        texture_count = len(m.texture_slots.keys())
        if texture_count == 0:
            s.set_texturing(cls.Shading.Texturing.COLORED)
        elif texture_count == 1:
            s.set_texturing(cls.Shading.Texturing.TEXTURED)
            cls.assert_texture_2d(m.texture_slots[0].texture)
        else:
            cls.show("Unsupported number of textures in material: " + m.name)
        if m.specular_intensity > 0.001:
            s.set_speculating(cls.Shading.Speculating.SPECULATED)
        else:
            s.set_speculating(cls.Shading.Speculating.MATTE)
        if m.use_cast_shadows:
            if m.use_shadows:
                s.set_shadowing(cls.Shading.Shadowing.FULL)
            else:
                s.set_shadowing(cls.Shading.Shadowing.CASTER)
        else:
            if m.use_shadows:
                cls.show(
                    "This is impossible that a shader make no shadow but use shadow-map")
            else:
                s.set_shadowing(cls.Shading.Shadowing.SHADOWLESS)
        if cls.STRING_CUTOFF in m:
            s.set_transparency(cls.Shading.Transparency.CUTOFF)
        elif cls.STRING_TRANSPARENT in m:
            s.set_transparency(cls.Shading.Transparency.TRANSPARENT)
        k = s.to_int()
        if k not in cls.shaders:
            cls.shaders[k] = [0, s]
        return k

    @classmethod
    def assert_material_face(cls, face, m):
        if len(m.texture_slots.keys()) == 1:
            error = "Texture in material " + m.name + " is not set correctly"
            txt = m.texture_slots[0]
            if txt is None:
                cls.show(error)
            txt = txt.texture
            if txt is None:
                cls.show(error)
            img = txt.image
            if img is None:
                cls.show(error)
            img = bpy.path.abspath(img.filepath_raw).strip()
            if img is None or len(img) == 0:
                cls.show(error)
            if not img.endswith(".png"):
                cls.show("Only PNG file is supported right now! change " + img)
            if not img.endswith("-" + face + ".png"):
                cls.show("File name must end with -" + face + ".png in " + img)
            if face == "up":
                cls.assert_texture_cube(img)
            return cls.Shading.EnvironmentMapping.BAKED
        elif len(m.texture_slots.keys()) > 1:
            cls.show("Material " + m.name +
                     " has more than expected textures.")
        elif not m.raytrace_mirror.use or \
                m.raytrace_mirror.reflect_factor < 0.001:
            cls.show("Material " + m.name + " does not set reflective.")
        return cls.Shading.EnvironmentMapping.REALTIME

    @classmethod
    def read_material_slot(cls, s):
        environment = None
        for f in cls.STRING_CUBE_TEXTURE_FACES:
            found = 0
            face_mat = None
            for m in s.keys():
                mat = s[m].material
                if mat.name.endswith("-" + f):
                    face_mat = mat
                    found += 1
            if found > 1:
                cls.show("More than 1 material found with property " + f)
            if found < 1:
                cls.show("No material found with name " + f)
            face_env = cls.assert_material_face(f, face_mat)
            if environment is None:
                environment = face_env
            elif environment != face_env:
                cls.show("Material " + face_mat + " is different than others.")
        for m in s.keys():
            mat = s[m].material
            found = True
            for f in cls.STRING_CUBE_TEXTURE_FACES:
                if mat.name.endswith("-" + f):
                    found = False
                    break
            if found:
                return cls.read_material(mat, environment=environment)
        cls.show("Unexpected")

    @classmethod
    def assert_model_materials(cls, m):
        if m.type != 'MESH':
            return
        for c in m.children:
            cls.assert_model_materials(c)
        if cls.STRING_DYNAMIC_PART in m or m.parent is None:
            material_count = len(m.material_slots.keys())
            if material_count != 0:
                cls.show("Dynamic/RootStatic model must have occlusion mesh " +
                         "at its root that does not have any material, your '" +
                         m.name + "' model has to not have any material " +
                         "but it has " + str(material_count) + " material(s).")
            else:
                return
        if len(m.material_slots.keys()) == 1:
            cls.read_material(m.material_slots[0].material)
        else:
            cls.show("Unexpected number of materials in model " + m.name)

    @classmethod
    def read_model(cls, m):
        if m.parent is not None:
            return
        if m.name in cls.models:
            return
        cls.assert_model_dynamism(m)
        cls.assert_model_materials(m)
        cls.models[m.name] = [0, cls.last_model_id]
        cls.last_model_id += 1

    @classmethod
    def read_light(cls, o):
        l = o.data
        if l.type != 'SUN':
            cls.show("Only sun light is supported, change " + l.name)
        if l.name not in cls.lights:
            cls.lights[l.name] = [0, cls.last_light_id]
            cls.last_light_id += 1

    @classmethod
    def read_camera(cls, c):
        if c.name not in cls.cameras:
            cls.cameras[c.name] = [0, cls.last_camera_id]
            cls.last_camera_id += 1

    @classmethod
    def read_speaker(cls, s):
        speaker_type = cls.SPEAKER_TYPE_OBJECT
        if s.parent is None:
            speaker_type = cls.SPEAKER_TYPE_MUSIC
        name = bpy.path.abspath(s.data.sound.filepath)
        if name in cls.speakers:
            if cls.speakers[name][2] != speaker_type:
                cls.show("Same file for two different speaker, file: " + name)
        else:
            cls.speakers[name] = [0, cls.last_speaker_id, speaker_type]
            cls.last_speaker_id += 1

    @classmethod
    def read_object(cls, o):
        if o.type == 'MESH':
            return cls.read_model(o)
        if o.type == 'CAMERA':
            return cls.read_camera(o)
        if o.type == 'LAMP':
            return cls.read_light(o)
        if o.type == 'SPEAKER':
            return cls.read_speaker(o)

    @classmethod
    def read_scenes(cls):
        for s in bpy.data.scenes:
            if s.name in cls.scenes:
                continue
            for o in s.objects:
                cls.read_object(o)
            cls.scenes[s.name] = [0, cls.last_scene_id]
            cls.last_scene_id += 1

    @classmethod
    def write_tables(cls):
        cls.write_shaders_table()
        cls.gather_cameras_offsets()
        cls.gather_speakers_offsets()
        cls.gather_lights_offsets()
        cls.gather_textures_offsets()
        cls.gather_models_offsets()
        cls.gather_scenes_offsets()
        cls.write_offset_array(cls.cameras_offsets)
        cls.write_offset_array(cls.speakers_offsets)
        cls.write_offset_array(cls.lights_offsets)
        cls.write_offset_array(cls.textures_offsets)
        cls.write_offset_array(cls.models_offsets)
        cls.write_offset_array(cls.scenes_offsets)

    @classmethod
    def initialize_shaders(cls):
        s = cls.Shading(cls)
        s.print_all_enums()
        cls.shaders = dict()  # Id<discret>: [offset, obj]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.WHITE_POS)
        cls.shaders[s.to_int()] = [0, s]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.WHITE_POS_NRM)
        cls.shaders[s.to_int()] = [0, s]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.WHITE_POS_UV)
        cls.shaders[s.to_int()] = [0, s]
        s = cls.Shading(cls)
        s.set_reserved(cls.Shading.Reserved.WHITE_POS_NRM_UV)
        cls.shaders[s.to_int()] = [0, s]

    @classmethod
    def write_file(cls):
        cls.initialize_shaders()
        cls.textures = dict()  # filepath: [offest, id<con>, type]
        cls.last_texture_id = 0
        cls.scenes = dict()  # name: [offset, id<con>]
        cls.last_scene_id = 0
        cls.models = dict()  # name: [offset, id<con>]
        cls.last_model_id = 0
        cls.cameras = dict()  # name: [offset, id<con>]
        cls.last_camera_id = 0
        cls.lights = dict()  # name: [offset, id<con>]
        cls.last_light_id = 0
        cls.speakers = dict()  # name: [offset, id<con>, type]
        cls.last_speaker_id = 0
        cls.read_scenes()
        cls.write_bool(sys.byteorder == 'little')
        tables_offset = cls.out.tell()
        cls.write_tables()
        cls.write_shaders()
        cls.write_cameras()
        cls.write_speakers()
        cls.write_lights()
        cls.write_textures()
        cls.write_models()
        cls.write_scenes()
        cls.out.flush()
        cls.out.seek(tables_offset)
        cls.write_tables()
        cls.out.flush()
        cls.out.close()
        cls.rust_code.flush()
        cls.rust_code.close()

    class Exporter(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
        """This is a plug in for Gearoenix 3D file format"""
        bl_idname = "gearoenix_exporter.data_structure"
        bl_label = "Export Gearoenix 3D"
        filename_ext = ".gx3d"
        filter_glob = bpy.props.StringProperty(
            default="*.gx3d",
            options={'HIDDEN'}, )
        export_vulkan = bpy.props.BoolProperty(
            name="Enable Vulkan",
            description="This item enables data exporting for Vulkan engine.",
            default=False, options={'ANIMATABLE'}, subtype='NONE', update=None)
        export_metal = bpy.props.BoolProperty(
            name="Enable Metal",
            description="This item enables data exporting for Metal engine.",
            default=False, options={'ANIMATABLE'}, subtype='NONE', update=None)

        def execute(self, context):
            if not (Gearoenix.check_env()):
                return {'CANCELLED'}
            try:
                Gearoenix.export_vulkan = bool(self.export_vulkan)
                Gearoenix.export_metal = bool(self.export_metal)
                Gearoenix.out = open(self.filepath, mode='wb')
                Gearoenix.rust_code = open(self.filepath + ".rs", mode='w')
            except:
                cls.show('file %s can not be opened!' % self.filepath)
            Gearoenix.write_file()
            return {'FINISHED'}

    def menu_func_export(self, context):
        self.layout.operator(
            Gearoenix.Exporter.bl_idname, text="Gearoenix 3D Exporter (.gx3d)")

    @classmethod
    def register(cls):
        bpy.utils.register_class(cls.ErrorMsgBox)
        bpy.utils.register_class(cls.Exporter)
        bpy.types.INFO_MT_file_export.append(cls.menu_func_export)

    class TmpFile:
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


if __name__ == "__main__":
    Gearoenix.register()
