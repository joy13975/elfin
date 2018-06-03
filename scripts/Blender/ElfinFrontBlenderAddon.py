import bpy
from bpy.props import *

bl_info = {'name': 'Elfin Front', 'category': 'Elfin'}

# Addon design notes
#   * Each separate object is a separate chain
#   * There should be no faces in any object
#       * Code simply ignores faces
#       x Provide a face delete operator 
#   * There should be no discontinuities in an object
#       * Code should verify this
#   x Unit conversion: 1 blender unit is 10 A, or 1 nm
#       x In other words 1 unit in blender is 10 pymol units
#   * Module avatar generation:
#       * Singles and pairs exported as OBJ from Pymol
#           * Pre-process OBJs
#       * How to do avatars in viewport elegantly?
#

class ElfinPropertyGroup(bpy.types.PropertyGroup):
    PpSrcDir = bpy.props.StringProperty(subtype='DIR_PATH', default='//..\\res\\aligned_obj\\')
    PpDstDir = bpy.props.StringProperty(subtype='DIR_PATH', default='//..\\res\\aligned_blend\\')
    PpDecimateRatio = bpy.props.FloatProperty(default=0.1, min=0.00, max=1.00)

class ElfinDebugPanel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_label = 'Debug'
    bl_context = 'objectmode'
    bl_category = 'Elfin'

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        col = row.column()
        col.operator('elfin.reset', text='Reset Properties')
        col.operator('elfin.delete_faces', text='Delete faces (selection)')
        col.operator('elfin.preproess_obj', text='Preprocess object (selection)')

class ElfinPreprocessPanel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_label = 'Preprocess'
    bl_context = 'objectmode'
    bl_category = 'Elfin'

    def draw(self, context):
        scn = context.scene
        layout = self.layout

        row = layout.row(align=True)
        col = row.column()
        col.prop(scn.ElfinFront, 'PpSrcDir', text='Source')
        col.prop(scn.ElfinFront, 'PpDstDir', text='Destination')
        col.prop(scn.ElfinFront, 'PpDecimateRatio', text='Decimate Ratio')
        col.operator('elfin.preproess_all', text='Preprocess')

class ElfinExportPanel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_label = 'Export'
    bl_context = 'objectmode'
    bl_category = 'Elfin'


    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        col = row.column()
        col.operator('elfin.export', text='Export to .ei')

class ElfinExportOperator(bpy.types.Operator):
    bl_idname = 'elfin.export'
    bl_label = 'Export as Elfin input'

    def execute(self, context):
        # Each separate object is a separate chain
        print('Unimplemented')

        return {'FINISHED'}

class ElfinPreprocessAllOperator(bpy.types.Operator):
    bl_idname = 'elfin.preproess_all'
    bl_label = 'Preprocess module obj files'

    def execute(self, context):
        print('Unimplemented')
        return {'FINISHED'}

class ElfinPreprocessObjOperator(bpy.types.Operator):
    bl_idname = 'elfin.preproess_obj'
    bl_label = 'Preprocess module object'

    def execute(self, context):
        for obj in bpy.context.selected_objects:
            obj.scale = (.1, .1, .1)
            bpy.context.scene.objects.active = obj
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
            bpy.ops.mesh.remove_doubles()
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.modifier_add(type='DECIMATE')
            bpy.context.object.modifiers['Decimate'].ratio = context.scene.ElfinFront['PpDecimateRatio']
            bpy.ops.object.modifier_apply(apply_as='DATA', modifier='Decimate')
        return {'FINISHED'}

class ElfinDeleteFacesOperator(bpy.types.Operator):
    bl_idname = 'elfin.delete_faces'
    bl_label = 'Delete Faces (selected only)'
    
    def execute(self, context):
        selObjs = bpy.context.selected_objects
        for obj in selObjs:
            bpy.context.scene.objects.active = obj
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.delete(type='ONLY_FACE')
            bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}

class ElfinResetOperator(bpy.types.Operator):
    bl_idname = 'elfin.reset'
    bl_label = 'Reset Elfin Front properties'

    def execute(self, context):
        scn = context.scene
        for k in scn.ElfinFront.keys():
            scn.ElfinFront.property_unset(k)
        return {'FINISHED'}

def register():
    bpy.utils.register_module(__name__)
    bpy.types.Scene.ElfinFront = bpy.props.PointerProperty(type=ElfinPropertyGroup)
    print('Elfin Front Addon registered')
    
def unregister():
    bpy.utils.unregister_module(__name__)
    del bpy.types.Scene.ElfinFront
    print('Elfin Front Addon unregistered')
    
if __name__ == '__main__':
    register()