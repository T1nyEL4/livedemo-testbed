"""Parametric visual reconstruction. Run with the adjacent Mechanical Explorer skill."""
from pathlib import Path
from math import sin, cos, tau, pi, radians
import json
import sys

import bpy
import bmesh
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parent
skill = ROOT.parent / "mechanical-darkmode"
if not skill.exists():
    skill = ROOT.parent / "mechanical-darkmode-clean copy"
sys.path.insert(0, str(skill / "scripts"))
from c3d import anim, core, joints, materials, shapes

OUT = Path(core.args().get("out-dir", str(ROOT))).resolve()
OUT.mkdir(parents=True, exist_ok=True)

scene = core.reset_scene((.049, .032, .073))
bpy.context.preferences.filepaths.save_version = 0
MM = .001
PRODUCT = "Tissot T-Complication Squelette"
parts, groups, objects = [], [], {}
families = {
    "case": ("Case and glazing", "Protects the movement while exposing both sides."),
    "dial": ("Chapter ring and indications", "Makes hours, minutes and subsidiary seconds readable."),
    "structure": ("Skeletonized movement frame", "Locates wheel pivots and carries the winding and regulating assemblies."),
    "winding": ("Manual winding", "Transmits input from the crown to the mainspring barrel."),
    "train": ("Wheel train", "Transfers torque from the barrel toward the escapement and hands."),
    "regulation": ("Escapement and balance", "Meters the release of energy from the train."),
    "strap": ("Strap and clasp", "Fastens the watch to the wrist."),
}

def point(x, depth, z):
    return (x*MM, -depth*MM, z*MM)

def mat(preset, color, name):
    return materials.get(preset, color=color, name=name)

steel = mat("aluminum_brushed", "#c7ced8", "Satin stainless steel")
polish = mat("stainless_steel", "#ced7e4", "Polished stainless steel")
bridge = mat("aluminum_brushed", "#ced4d8", "Satin skeleton bridge faces")
bridge_wall = mat("stainless_steel", "#535d68", "Machined skeleton cut walls")
movement_base = mat("stainless_steel", "#353e4a", "Dark movement perimeter")
barrel_finish = mat("stainless_steel", "#85919d", "Satin barrel steel")
edge = mat("painted_metal", "#252c38", "Graphite chapter ring")
blue = mat("stainless_steel", "#174b83", "Blued steel")
white = mat("abs_satin", "#f0f5ff", "Luminous inlay and printing")
gold = mat("aluminum_brushed", "#e6a941", "Brass wheels")
ruby = mat("abs_satin", "#a6084b", "Synthetic ruby")
dark = mat("leather", "#10131a", "Black calf leather")
grain = mat("leather", "#10141b", "Raised leather grain")
thread = mat("abs_satin", "#343945", "Strap stitching")
glass = mat("glass_clear", "#eef7ff", "Clear sapphire")
black = mat("rubber", "#14181d", "Gasket")
for material, metal, rough in [(steel,1,.32),(polish,1,.22),(bridge,1,.36),(blue,1,.28),(gold,1,.31),(ruby,0,.22)]:
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Metallic"].default_value = metal
    shader.inputs["Roughness"].default_value = rough

glass.node_tree.nodes.get("Principled BSDF").inputs["Alpha"].default_value = .026

def register(obj, pid, label, material, family, function, offset, parent=None,
             evidence="observed", note=None, relation="mounts to", motion=None, stage=None):
    obj = core.part(obj, pid, material, parent=objects.get(parent), label=label)
    objects[pid] = obj
    note = note or ("Exact-watch factory photos show the appearance; hidden dimensions are estimated."
                    if evidence == "observed" else
                    "The ETA 6497-1 technical communication supports the function; Squelette-specific dimensions and interfaces are estimated.")
    parts.append(dict(id=pid, label=label, function=function, evidence=evidence, evidenceNote=note,
                      assembly=family, parent=parent, interfaces=(
                          [dict(target=parent, type=relation, evidence="inferred")] if parent else []),
                      motion=motion or {"kind":"fixed"}))
    start, end = stage or {"case": (0,.43), "strap": (0,.42), "dial": (.19,.65),
                          "structure": (.32,.84), "winding": (.36,.90),
                          "train": (.52,1), "regulation": (.54,1)}[family]
    groups.append(dict(id=pid,label=label,parts=[pid],offset=[v*MM for v in offset],
                       start=start,end=end,evidence=evidence,note=note))
    return obj

def interface(pid, target, verb):
    record = next(record for record in parts if record["id"] == pid)
    record["interfaces"].append(dict(target=target,type=verb,evidence="inferred"))

def solid(name, outline, depth, thick, bevel=0):
    vertices = [point(x, depth+d, z) for d in (-thick/2, thick/2) for x,z in outline]
    n = len(outline)
    faces = [tuple(reversed(range(n))), tuple(range(n, 2*n))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    ob = core.link(bpy.data.objects.new(name, mesh))
    if bevel:
        bevel_edges(ob, bevel)
    return ob

def bevel_edges(obj, width):
    mod = obj.modifiers.new("Edge breaks", "BEVEL")
    mod.width = width*MM
    mod.segments = 2
    mod.limit_method = "ANGLE"
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return obj

def circle(profile, center=(0,0), axis="-Y", segments=128):
    return core.smooth(shapes.lathe("turned", [(r*MM,d*MM) for r,d in profile],
                                    center=point(center[0],0,center[1]),axis=axis,segments=segments))

def ring(inner, outer, lo, hi, center=(0,0), chamfer=.12, segments=128):
    b = min(chamfer, (hi-lo)/3, (outer-inner)/3)
    return circle([(inner,lo+b),(inner+b,lo),(outer-b,lo),(outer,lo+b),
                   (outer,hi-b),(outer-b,hi),(inner+b,hi),(inner,hi-b),(inner,lo+b)],
                  center,segments=segments)

def disk(x,z,d,r,t, bevel=.06, segments=48, axis="-Y"):
    return shapes.cylinder("disc",r*MM,t*MM,point(x,d,z),axis=axis,
                           bevel=bevel*MM,segments=segments)

def box(x,z,d,w,h,t,r=.12):
    return shapes.rounded_box("block",(w*MM,t*MM,h*MM),r*MM,point(x,d,z),segments=3)

def cut(obj, cutters):
    for tool in cutters:
        shapes.boolean(obj, tool)
    return obj

def text(body,x,z,d,height, angle=0, rear=False):
    data = bpy.data.curves.new(body,"FONT")
    data.body, data.align_x, data.align_y = body, "CENTER", "CENTER"
    data.size, data.extrude = height*MM, .014*MM
    obj = core.link(bpy.data.objects.new(body,data))
    obj.location = point(x,d,z)
    obj.rotation_euler = (Matrix.Rotation(radians(-90 if rear else 90),4,"X") @
                          Matrix.Rotation(radians(180 if rear else 0),4,"Z") @
                          Matrix.Rotation(radians(angle),4,"Z")).to_euler()
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj.select_set(False)
    return obj

def merge(meshes):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    meshes[0].select_set(False)
    return meshes[0]

def polar(angle,r):
    return sin(angle)*r, cos(angle)*r

def rotation(x,d,z,limits):
    return dict(kind="rotation",space="model",axis=[0,0,1],pivot=[x*MM,z*MM,d*MM],
                range=[radians(v) for v in limits],unit="radians",
                note="Axis follows the indicated pivot; range describes the illustrative clip.")

case = circle([(19.35,-4.55),(20.03,-4.55),(21.10,-4.01),(21.5,-3.23),
               (21.5,3.12),(21.18,3.77),(20.7,4.02),(19.55,4.02),
               (19.35,3.8),(19.35,-4.55)])
cut(case,[disk(20.5,0,-.22,1.06,5,axis="X")])
register(case,"case_middle","Stainless steel case middle",steel,"case",
         "Locates the movement and carries the front bezel, lugs and crown.",(0,0,-5))
register(circle([(18.8,3.83),(20.7,3.83),(21.18,4.04),(21.24,4.54),
                 (20.81,5.06),(19.52,5.63),(19.15,5.71),(18.8,5.38),(18.8,3.83)]),
         "bezel","Brushed front bezel",steel,"case","Retains the front sapphire.",(0,0,21),"case_middle")
register(disk(0,0,5.49,18.72,.98,.16,128),"front_crystal","Front sapphire crystal",glass,"case",
         "Protects the exposed display and lets light pass through it.",(0,0,34),"bezel")
register(ring(18.78,19.03,4.72,4.99),"front_gasket","Front crystal gasket",black,"case",
         "Seals the front crystal seat.",(0,0,15),"bezel",evidence="inferred")
register(ring(16.86,20.35,-6.01,-4.66,chamfer=.31),"caseback","Exhibition caseback",steel,"case",
         "Retains the rear display window and closes the case.",(0,0,-24),"case_middle")
register(merge([text("TISSOT",0,18.45,-6.05,1.61,rear=True),
                text("SAPPHIRE CRYSTAL",13.55,12.8,-6.05,.84,-45,rear=True),
                text("STAINLESS STEEL",-13.58,12.8,-6.05,.84,45,rear=True),
                text("T070405 A",0,-18.45,-6.05,1.11,rear=True)]),
         "caseback_markings","Caseback markings",edge,"case",
         "Identifies the case reference, sapphire glazing and stainless steel.",(0,0,-26),"caseback")
register(disk(0,0,-5.28,16.81,1.24,.13,128),"rear_crystal","Rear sapphire crystal",glass,"case",
         "Provides a view of the movement from the back.",(0,0,-33),"caseback")
register(ring(18.08,19.22,-4.55,-4.20),"movement_spacer","Movement locating ring",black,"structure",
         "Centers the movement in the case.",(0,0,-10),"case_middle",evidence="inferred")

# Lugs and two curved straps. The clasp closes the two ends underneath the watch.
def strap_depth(z):
    return -2.35 - 12.5*max(0,(abs(z)-23)/13)**1.63

for sy, end in [(1,"upper"),(-1,"lower")]:
    lug_meshes = []
    for sx in [-1,1]:
        outline = [(sx*x,sy*z) for x,z in [(10.97,16.3),(17.1,11.7),(17.12,15.3),
                                           (14.3,20.3),(12.1,25.05),(10.99,25.48)]]
        lug_meshes.append(solid("lug",outline,-.95,5.15,.49))
    lug = register(merge(lug_meshes),f"{end}_lugs",f"{end.title()} lug pair",steel,"case",
                   "Supports the spring bar at the 22 mm strap fitting.",(0,sy*7,-3),"case_middle")
    register(disk(0,sy*23.95,-2.35,.66,22.25,.14,32,axis="X"),f"{end}_bar",
             f"{end.title()} spring bar",polish,"strap","Pins the leather strap between the lugs.",
             (sy*18,sy*13,-2),lug.name,evidence="inferred")
    sections = []
    n = 31
    for i in range(n):
        z = sy*(19.8 + 16.25*i/(n-1))
        w = 10.91 - .85*i/(n-1) - 1.6*max(0,(i/(n-1)-.8)/.2)**2
        contours = [(-1,0),(-.97,.68),(-.86,1),(.86,1),(.97,.68),(1,0),(.98,-.52),
                    (.87,-.74),(-.87,-.74),(-.98,-.52)]
        sections.append([point(w*x,strap_depth(z)+1.52*y,z) for x,y in contours])
    ob = shapes.loft("leather",sections)
    ob = register(ob,f"{end}_strap",f"{end.title()} black leather strap",dark,"strap",
                  "Wraps around the wrist and connects to the clasp.",(0,sy*24,-13),f"{end}_bar")
    trim = []
    embossing = []
    for iz in range(5):
        z = sy*(23.2+2.52*iz)
        for column in range(3):
            x = (column-1)*5.3 + (.22 if iz%2 else -.22)
            embossing.append(box(x,z,strap_depth(z)+1.43,5.1,2.45,.32,.15))
    register(merge(embossing),f"{end}_emboss",f"{end.title()} leather embossing",grain,"strap",
             "Forms the visible raised grain of the leather.",(0,sy*28,-13),ob.name)
    for ix in (-1,1):
        for i in range(15):
            z = sy*(20.85+i*.97)
            x = ix*(9.75-.06*i-.95*max(0,(i-11)/3)**2)
            trim.append(box(x,z,strap_depth(z)+1.59,.19,.55,.15,.06))
    register(merge(trim),f"{end}_stitch",f"{end.title()} strap stitching",thread,"strap",
             "Holds the strap edge layers together.",(0,sy*31,-13),ob.name)

register(box(0,33.2,-13.45,20.3,4.8,1.65,.55),"clasp","Steel folding clasp cover",steel,"strap",
         "Covers the folding hardware that closes the strap.",(10,32,-26),"upper_strap")
register(text("T",0,33.2,-14.32,3.1,rear=True),"clasp_mark","Clasp emblem",edge,"strap",
         "Identifies the clasp.",(10,35,-25),"clasp")
for ix in (-1,1):
    register(solid("deployant",[(ix*x,z) for x,z in [(6,32),(9,32),(9,27),(7.6,22),(5.4,22)]],-15.1,1.1,.25),
             f"clasp_blade_{ix+2}","Folding clasp blade",polish,"strap",
             "Folds beneath the clasp cover to link the two strap ends.",(ix*8,23,-30),"clasp",evidence="inferred")

register(ring(17.60,18.78,3.17,4.17,chamfer=.17),"chapter_ring","Graphite chapter ring",edge,"dial",
         "Carries the minute graduations and twelve appliqué hour markers.",(0,0,14),"case_middle")
ticks=[]
for i in range(60):
    a = i*tau/60
    if i%5:
        x,z = polar(a,18.15)
        mark=box(0,0,0,.17,.72,.045,.017)
        mark.data.transform(Matrix.Translation(Vector(point(x,4.235,z))) @ Matrix.Rotation(a,4,"Y"))
        ticks.append(mark)
    else:
        x,z=polar(a,17.85)
        outline = []
        for u,v in [(-.58,-1.05),(.58,-1.05),(.47,1.02),(-.47,1.02)]:
            outline.append((x+u*cos(a)+v*sin(a),z-u*sin(a)+v*cos(a)))
        marker=register(solid("hour",outline,4.32,.27,.045),f"hour_marker_{i//5:02d}",
                        f"{i//5 or 12} o’clock appliqué",blue,"dial","Marks the hour on the chapter ring.",
                        (x*.59,z*.59,17),"chapter_ring")
        line = box(0,0,0,.34,1.69,.07,.028)
        line.data.transform(Matrix.Translation(Vector(point(x,4.50,z))) @ Matrix.Rotation(a,4,"Y"))
        register(line,f"hour_lume_{i//5:02d}",f"{i//5 or 12} o’clock lume",white,"dial",
                 "Bright inlay improves hour legibility.",(x*.68,z*.68,19),marker.name)
register(merge(ticks),"minute_scale","Minute graduations",white,"dial",
         "Divides the chapter ring into one-minute intervals.",(0,0,18),"chapter_ring")
for pid, label,x,z,d,h,a in [("swiss","SWISS",-3.0,-16.98,4.30,.69,-9),("made","MADE",3.0,-16.98,4.30,.69,9)]:
    register(text(label,x,z,d,h,a),pid,label,white,"dial","Prints the origin marking on the dial.",
             (0,-9,18),"chapter_ring")
plaque_outline = [(6.3,3.22),(16.7,3.22),(17.42,6.9),(16.8,7.8),(7.25,6.85),(6.2,5.83)]
register(solid("nameplate",plaque_outline,3.12,.42,.16),"nameplate","Graphite nameplate",edge,"dial",
         "Carries the Tissot signature on the open dial.",(12,2,16),"chapter_ring")
register(merge([text("TISSOT",11.9,5.77,3.37,1.85),text("1853",11.8,4.22,3.37,1.16)]),
         "signature","TISSOT 1853 signature",white,"dial","Identifies the watchmaker.",(13,3,18),"nameplate")

def plate(pid,label,outline,holes,d,t,function,offset,parent=None):
    ob=solid(pid,outline,d,t)
    cut(ob,[solid("opening",hole,d,t+2) for hole in holes])
    bevel_edges(ob,.115)
    result = register(ob,pid,label,bridge,"structure",function,offset,parent)
    result.data.materials.append(bridge_wall)
    if pid.startswith("rear_"):
        result.data.materials[0] = barrel_finish
    for face in result.data.polygons:
        if abs(face.normal.y) < .85:
            face.material_index = 1
    return result

register(ring(16.65,18.28,-.94,.33,chamfer=.12),"mainplate","Skeleton mainplate perimeter",movement_base,"structure",
         "Locates the skeletonized movement and its cross members.",(0,0,-4),"movement_spacer")
plate("dial_web","Openworked dial-side plate",
      [(-16.7,8.9),(-12.9,11.5),(-12.4,9.1),(-13.1,6.0),(-13.6,4.1),
       (-11.5,3.5),(-9.1,5.0),(-7.9,3.2),(-6.0,3.3),(-4.7,1.9),(-4.8,-.6),
       (-4.0,-3.3),(-2.3,-5.1),(.3,-5.8),(3.1,-5.0),(5.2,-2.8),(6.2,.0),
       (8.1,1.3),(11.0,-.5),(13.5,-3.8),(16.1,-6.4),(15.5,-9.3),
       (12.5,-10.1),(11.0,-8.1),(8.6,-8.7),(8.1,-12.7),(6.0,-16.9),
       (2.7,-17.8),(2.1,-13.1),(.8,-10.9),(-1.5,-10.0),(-2.6,-12.3),
       (-4.6,-15.8),(-7.7,-16.1),(-11.3,-13.8),(-14.7,-10.6),(-16.3,-8.1),
       (-13.8,-7.7),(-11.5,-9.3),(-9.8,-8.6),(-7.7,-5.0),(-8.4,-3.5),
       (-10.2,-4.4),(-12.8,-3.2),(-14.3,-1.9),(-16.8,-1.9),(-17.2,2.2)],
      [[(-15.8,2.1),(-14.0,3.0),(-12.5,2.0),(-13.0,.5),(-14.6,.2)],
       [(-9.4,2.2),(-7.8,2.5),(-7.2,1.0),(-7.8,-1.3),(-9.3,-2.4),(-10.0,-1.5)],
       [(-7.0,-5.5),(-5.6,-4.3),(-4.3,-5.9),(-4.9,-7.0),(-6.0,-6.8)],
       [(-9.8,-10.3),(-8.6,-8.9),(-7.5,-9.6),(-6.7,-11.6),(-7.9,-12.5)],
       [(3.8,-14.9),(3.4,-12.2),(5.0,-11.8),(6.1,-13.2),(5.6,-15.1)],
       [(2.2,-6.8),(3.8,-5.9),(4.6,-6.6),(3.8,-7.7),(2.4,-7.9)],
       [(6.0,-5.2),(7.2,-4.5),(8.2,-5.3),(8.0,-6.8),(6.7,-6.5)]],
      1.21,.97,"Supports the offset seconds pivot and exposes the barrel and wheels between three projecting arms.",(0,-4,7),"mainplate")
plate("balance_cock","Dial-side balance cock",
      [(-8.8,15.5),(-3.2,16.9),(-2,12),(-.3,9.1),(.6,5),(-3.4,4),(-8,4.9),(-10,7.7),(-10.4,11)],
      [[(-7.9,13.7),(-5.9,14.9),(-5.4,11.8),(-7.8,11.2)]],
      1.65,.8,"Supports the upper balance staff jewel.",(-9,13,12),"mainplate")
plate("setting_bridge","Winding and setting bridge",
      [(2.5,10),(3.3,12),(9.3,14.6),(13.5,12.3),(15.9,8.1),(13,4.7),(10.6,1.4),
       (8.9,1.5),(8.9,5.5),(6.6,9.4)],
      [[(4,10.6),(6.3,12.2),(7.8,10.7),(7,9.2)]],
      1.92,.78,"Carries parts of the setting transmission beside the stem.",(13,11,9),"mainplate")
plate("rear_train_bridge","Rear train bridge",
      [(-16,7),(-13,10),(-9.3,8),(-6.4,5),(-4,3.5),(-3.1,.5),(-5.2,-3.1),(-8,-4.6),
       (-9.2,-7.1),(-14.2,-13),(-17,-8),(-14,-5),(-16,-2),(-15.2,2)],
      [[(-13,6.5),(-10.7,6.7),(-8.6,4.4),(-11,4)],
       [(-13.2,1.9),(-11.4,3),(-10.8,.6),(-12.8,-.9)],
       [(-10.2,-2.6),(-8.2,-1.7),(-7,-2.8),(-9.6,-4.3)]],
      -3.28,.83,"Locates the lower pivots of the going train.",(-14,2,-16),"mainplate")
plate("rear_barrel_bridge","Rear barrel bridge",
      [(1.2,2),(4,1),(5.3,-3.3),(10.4,-5.9),(15.3,-8),(12.6,-13.6),(6,-16.4),
       (-1.5,-17),(1.4,-12),(2,-9),(1.4,-5),(-1.8,-1)],
      [[(2.4,-3),(3.8,-2.6),(4.1,-5.4),(2.8,-5.7)],[(3,-13),(5.3,-12.7),(5,-15),(3.5,-15.4)]],
      -3.43,.87,"Carries the winding barrel arbor and click.",(10,-13,-18),"mainplate")
plate("rear_balance_cock","Rear balance cock",
      [(-2,16),(2.8,16),(2.5,13),(-1.2,10.4),(-3.2,8.2),(-5.4,8.95),(-5.2,11.5)],
      [],-3.10,.69,"Supports the rear balance jewel and regulator.",(-4,16,-16),"mainplate")

def gear(x,z,d,r,t,count, hole=True):
    outline=[]
    for i in range(count):
        for f,drop in [(0,.35),(.22,0),(.62,0),(.86,.35)]:
            a = tau*(i+f)/count
            outline.append((x+cos(a)*(r-drop),z+sin(a)*(r-drop)))
    ob=solid("wheel",outline,d,t)
    if hole:
        cutters=[]
        for i in range(3):
            a=i*tau/3+.26
            loop=[(x+radius*r*cos(a+ang),z+radius*r*sin(a+ang))
                  for radius,angles in [(.72,[j*.135 for j in range(-5,6)]),
                                       (.32,[j*.135 for j in range(5,-6,-1)])] for ang in angles]
            cutters.append(solid("spoke_window",loop,d,t+2))
        cut(ob,cutters)
    return ob

def wheel(pid,label,x,z,d,r,t,count,material,family,function,offset,parent="mainplate",ranges=None):
    return register(gear(x,z,d,r,t,count,r>2.3),pid,label,material,family,function,offset,parent,
                    evidence="inferred",motion=rotation(x,d,z,ranges) if ranges else {"kind":"unknown"})

wheel("barrel","Mainspring barrel",4.45,-8.2,-2.38,8.18,1.10,77,barrel_finish,"winding",
      "Contains the mainspring and delivers torque to the going train.",(15,-14,-10))
register(ring(7.11,7.87,-1.81,-1.76,(4.45,-8.2)), "barrel_cap","Barrel cover",polish,"winding",
         "Closes the mainspring barrel around the arbor.",(13,-16,-3),"barrel",evidence="inferred")
wheel("ratchet_wheel","Ratchet wheel",4.45,-8.2,-3.98,6.75,.49,60,steel,"winding",
      "Winds the barrel arbor and works against the click.",(18,-15,-24),"barrel")
wheel("crown_wheel","Crown wheel",10.4,-.05,-3.88,4.18,.46,40,steel,"winding",
      "Transmits the winding stem's input to the ratchet wheel.",(23,-1,-20))
register(solid("click",[(1,-14.2),(2.6,-13.9),(4.6,-14.8),(3,-15.5),(1.3,-15.5)],-3.95,.46,.14),
         "click","Ratchet click",polish,"winding","Prevents the ratchet wheel from unwinding through the crown.",
         (4,-23,-24),"rear_barrel_bridge",evidence="inferred")
wheel("center_wheel","Center wheel",0,0,-.61,5.65,.47,59,gold,"train",
      "Receives torque from the barrel and carries the center arbor.",(2,0,-10))
wheel("third_wheel","Third wheel",-6.02,-3.13,-1.51,4,.45,48,gold,"train",
      "Transfers torque between the center and fourth wheels.",(-12,-9,-10))
wheel("fourth_wheel","Fourth wheel",-10.2,.04,-.81,3.89,.49,48,gold,"train",
      "Drives the escape pinion and carries the small-seconds indicator.",(-18,2,-9))
wheel("escape_wheel","Escape wheel",-10.15,4.94,-1.68,2.37,.30,15,polish,"regulation",
      "Releases a tooth when the pallet fork unlocks.",(-20,10,-9))
wheel("minute_wheel","Minute wheel",2.26,4.24,2.56,3.65,.32,40,gold,"train",
      "Provides the reduction between the cannon pinion and hour wheel.",(10,11,8))
wheel("hour_wheel","Hour wheel",0,0,1.99,4.36,.36,45,gold,"train",
      "Carries the hour hand around the center arbor.",(2,2,11))
for pid,x,z,d,r,host,axis in [
    ("cannon_pinion",0,0,2.78,1.02,"center_wheel","-Y"),
    ("sliding_pinion",13.58,0,.1,1.31,"mainplate","X"),
    ("winding_pinion",15.36,0,.1,1.52,"mainplate","X")]:
    ob=gear(0,0,0,r,.73,14,False)
    transform=Matrix.Rotation(pi/2,4,"Z") if axis=="X" else Matrix.Identity(4)
    ob.data.transform(Matrix.Translation(Vector(point(x,d,z))) @ transform)
    register(ob,pid,pid.replace("_"," ").title(),polish,"winding" if axis=="X" else "train",
             {"cannon_pinion":"Couples the center arbor to the minute hand.",
              "sliding_pinion":"Selects winding or setting as the stem moves.",
              "winding_pinion":"Transmits stem rotation into the winding train."}[pid],
             (x*.62,4,8),host,evidence="inferred")
register(disk(18,0,-.22,.49,10.1,.10,32,axis="X"),"stem","Winding stem",polish,"winding",
         "Connects the external crown to the winding and setting pinions.",(20,0,0),"case_middle",evidence="inferred")
# Flutes are cut into the turned crown, following the crown axis.
crown=shapes.lathe("crown",[(0,0),(.00278,0),(.00305,.00024),(.00309,.00221),
                            (.0028,.00276),(.00249,.0029),(0,.0029)],
                   center=point(21.91,-.22,0),axis="X",segments=120)
cut(crown,[disk(23.05,sin(a)*3.06,-.22+cos(a)*3.06,.23,2.46,.025,12,axis="X")
           for a in [i*tau/32 for i in range(32)]])
register(crown,"crown","Fluted winding crown",polish,"winding",
         "Lets the wearer wind the mainspring and set the hands.",(31,0,0),"stem")
register(box(24.86,0,-.22,.10,1.83,.37,.035),"crown_inset","Crown cap detail",steel,"winding",
         "Provides the raised cap detail at the crown face.",(34,0,0),"crown")

# Three spokes are integrated into the balance rim, along with the central hub.
bx,bz,bd=-4.25,9.60,-1.25
balance=ring(6.33,6.68,bd-.16,bd+.16,(bx,bz),chamfer=.045,segments=96)
hub=disk(bx,bz,bd,.91,.38,.06,48)
for a in [.32,.32+tau/3,.32+2*tau/3]:
    path=[(bx+u*cos(a)-v*sin(a),bz+u*sin(a)+v*cos(a))
          for u,v in [(.52,-.25),(6.51,-.19),(6.51,.19),(.52,.25)]]
    arm=solid("balance_spoke",path,bd,.23)
    shapes.boolean(balance,arm,operation="UNION")
shapes.boolean(balance,hub,operation="UNION")
balance=register(balance,"balance","Gold balance wheel",gold,"regulation",
                 "Oscillates with the hairspring to regulate the escapement.",(-10,20,-9),"mainplate",
                 motion=rotation(bx,bd,bz,(-42,42)))
spiral=[]
for i in range(451):
    a=i/450*tau*9.2
    r=.67+i/450*3.28
    spiral.append(point(bx+r*cos(a),-1.95,bz+r*sin(a)))
spring=shapes.sweep("hairspring",spiral,.039*MM,segments=6,smooth_path=False)
register(spring,"hairspring","Coiled hairspring",polish,"regulation",
         "Applies restoring torque to the balance staff.",(-13,24,-15),"rear_balance_cock",
         evidence="inferred",motion={"kind":"unknown"})
fork_x,fork_z=-8.47,6.49
fork=register(solid("fork",[(-10.59,6.9),(-9.75,7.36),(-8.53,6.94),(-7.45,8.04),(-6.94,8.01),
                           (-7.63,6.86),(-7.19,6.48),(-7.67,6.05),(-8.49,6.29),(-9.74,5.57),(-10.22,5.82),
                           (-9.64,6.43)],-2.23,.24,.069),
              "pallet_fork","Swiss lever pallet fork",polish,"regulation",
              "Alternately locks the escape wheel and gives the balance an impulse.",(-22,15,-14),"mainplate",
              evidence="inferred",motion=rotation(fork_x,-2.23,fork_z,(-11,11)))
for i,(x,z) in enumerate([(-10.11,5.88),(-10.32,6.98)]):
    register(box(x,z,-2.29,.35,.43,.19,.045),f"pallet_{i+1}",f"Pallet stone {i+1}",ruby,"regulation",
             "Contacts the tips of the escape wheel teeth.",(-24-i*2,12+i*5,-16),"pallet_fork",evidence="inferred")

for side, rows in [
    ("front",[(bx,bz,2.39,.62,"balance_cock"),(-10.2,.04,1.90,.41,"dial_web"),
              (-10.15,4.94,1.87,.43,"dial_web"),(-6.1,-2.25,1.91,.46,"dial_web")]),
    ("rear",[(bx,bz,-3.65,.62,"rear_balance_cock"),(-10.2,.04,-3.94,.53,"rear_train_bridge"),
             (-10.15,4.94,-3.95,.54,"rear_train_bridge"),(-7.1,-2.3,-3.94,.55,"rear_train_bridge"),
             (0,0,-3.97,.61,"rear_barrel_bridge")])]:
    for i,(x,z,d,r,parent) in enumerate(rows):
        direction = 1 if side=="front" else -1
        setting=register(ring(r*.87,r+.22,d-.11,d+.11,(x,z),segments=40),
                         f"{side}_setting_{i+1}",f"{side.title()} jewel setting {i+1}",gold,"structure",
                         f"Retains the ruby bearing on the {parent.replace('_',' ')}.",
                         (x*1.5,z*1.4, direction*(13+i*1.1)),parent)
        register(disk(x,z,d+direction*.09,r*.83,.21,.076,40),f"{side}_jewel_{i+1}",
                 f"{side.title()} ruby bearing {i+1}",ruby,"structure",
                 f"Provides a low-friction pivot bearing on the {parent.replace('_',' ')}.",
                 (x*1.62,z*1.5,direction*(15+i*1.1)),setting.name)

screws=[(-6.7,14,2.14,"balance_cock"),(-8.92,7.2,2.11,"balance_cock"),(-2.1,7.0,2.14,"balance_cock"),
        (11.11,11.7,2.39,"setting_bridge"),(10.07,3.64,2.39,"setting_bridge"),
        (-14.7,1.1,1.82,"dial_web"),(-13.1,-8.2,1.82,"dial_web"),(-7.35,-12.9,1.82,"dial_web"),
        (10.37,-10.44,1.82,"dial_web"),(14.3,-3.0,1.82,"dial_web"),
        (-13.2,-8.59,-3.85,"rear_train_bridge"),(-14.0,6.25,-3.85,"rear_train_bridge"),
        (1.24,14.7,-3.57,"rear_balance_cock"),(8.95,-12,-4,"rear_barrel_bridge"),
        (4.45,-8.2,-4.36,"ratchet_wheel"),(10.4,-.05,-4.21,"crown_wheel")]
for i,(x,z,d,parent) in enumerate(screws):
    radius=.53 if i<14 else .94
    ob=disk(x,z,d,radius,.24,.055,32)
    cutter=box(x,z,d+(.13 if d>0 else -.13),radius*.32,radius*2.4,.20,.025)
    cut(ob,[cutter])
    register(ob,f"screw_{i+1:02d}",f"{parent.replace('_',' ').title()} screw",
             blue if i%5!=1 else polish,"structure",
             f"Fastens the {parent.replace('_',' ')} at the illustrated location.",
             (x*1.3,z*1.35,(15+(i%3)*2)*(1 if d>0 else -1)),parent)

# Open blue hands with white tips. Mesh apertures preserve the skeleton view.
def hand(pid,label,x,z,d,length,width,angle,host,function):
    a=radians(angle)
    def local(path):
        return [(x+u*cos(a)+v*sin(a),z-u*sin(a)+v*cos(a)) for u,v in path]
    ob=solid(pid,local([(0,-1.12),(.79,-.75),(width,.95),(width*.98,length*.25),
                        (0,length),(-width*.98,length*.25),(-width,.95),(-.79,-.75)]),d,.27,.055)
    cut(ob,[solid("hand_window",local([(-width*.48,.92),(width*.48,.92),
                  (width*.64,length*.31),(-width*.64,length*.31)]),d,.89)])
    ob=register(ob,pid,label,blue,"dial",function,(x*.85,z*.95,13+d*2),host,
                motion={"kind":"unknown"})
    inset=solid("inlay",local([(-width*.54,length*.39),(width*.54,length*.39),(0,length*.86)]),d+.181,.043)
    register(inset,pid+"_inlay",label+" luminous inlay",white,"dial","Increases indicator legibility.",
             (x*1.1,z*1.1,16+d*2),pid)
    return ob

hand("hour_hand","Hour hand",0,0,3.37,11.22,1.47,-61,"hour_wheel","Indicates the current hour.")
hand("minute_hand","Minute hand",0,0,3.87,16.81,1.33,49,"cannon_pinion","Indicates the current minute.")
hand("seconds_hand","Small seconds hand",-10.2,.04,2.42,4.79,.56,-132,"fourth_wheel","Indicates seconds on the subsidiary dial.")
register(disk(0,0,4.10,.78,.26,.072,48),"hand_cap","Central hand stack cap",blue,"dial",
         "Finishes the hand stack above the minute hand.",(0,0,26),"minute_hand")
register(text("SEC.",-11.33,.91,1.728,1.14,77),"seconds_mark","Subsidiary seconds legend",edge,"dial",
         "Identifies the offset small seconds indication.",(-16,3,10),"dial_web")

for pid,target,verb in [
    ("front_crystal","front_gasket","seals against"),("crown","winding_pinion","drives through stem"),
    ("crown_wheel","ratchet_wheel","drives"),("click","ratchet_wheel","locks reverse rotation of"),
    ("ratchet_wheel","barrel","winds"),("barrel","center_wheel","drives"),
    ("center_wheel","third_wheel","drives"),("third_wheel","fourth_wheel","drives"),
    ("fourth_wheel","escape_wheel","drives"),("escape_wheel","pallet_fork","intermittently engages"),
    ("pallet_fork","balance","impulses"),("hairspring","balance","supplies restoring torque to"),
    ("minute_wheel","hour_wheel","drives"),("cannon_pinion","minute_wheel","drives")]:
    interface(pid,target,verb)

# Keep the 2.5 Hz regulator readable while the going train displays 60× watch time.
b_joint=joints.knob(balance,"-Y",point(bx,bd,bz),(-255,255),"balance_pivot")
p_joint=joints.knob(fork,"-Y",point(fork_x,-2.23,fork_z),(-11,11),"pallet_pivot")
duration = 12
time_steps = [frame/30 for frame in range(duration*30+1)]

def wheel_track(pid, x, depth, z, angle_at, axis="-Y", seconds=duration):
    values = [(t, angle_at(t)) for t in time_steps if t <= seconds]
    angles = [angle for _, angle in values]
    limits = (min(angles), max(angles))
    obj = objects[pid]
    joint = joints.knob(obj, axis, point(x,depth,z), limits, pid+"_pivot")
    if axis == "-Y":
        next(part for part in parts if part["id"] == pid)["motion"] = rotation(x,depth,z,limits)
    return joint, values

def constant_rate(rate):
    return lambda t: rate*t


def accelerated_rate(rate):
    return constant_rate(rate * 60)

# The fourth-wheel arbor carries the seconds hand. The center arbor carries the
# cannon pinion and minute hand. Nominal rates are derived from indicated time.
tracks = [
    (b_joint, [(t, 245*sin(t*tau*2.5)) for t in time_steps]),
    (p_joint, [(t, 10*sin(t*tau*2.5)**7) for t in time_steps]),
    wheel_track("barrel",4.45,-2.38,-8.2,accelerated_rate(.0125)),
    wheel_track("center_wheel",0,-.61,0,accelerated_rate(-.1)),
    wheel_track("third_wheel",-6.02,-1.51,-3.13,accelerated_rate(.75)),
    wheel_track("fourth_wheel",-10.2,-.81,.04,accelerated_rate(-6)),
    wheel_track("escape_wheel",-10.15,-1.68,4.94,accelerated_rate(60)),
    wheel_track("minute_wheel",2.26,2.56,4.24,accelerated_rate(.025)),
    wheel_track("hour_wheel",0,1.99,0,accelerated_rate(-.1/12)),
]
# The ratchet rides on the barrel arbor, independently of the rotating drum.
core.set_parent(objects["ratchet_wheel"], objects["mainplate"])
anim.sequence("run_cycle",tracks,ease="linear")
anim.camera_clip("run_cycle",dict(view="front",azimuth=-8,elevation=5,parts=["bezel"],padding=1.18))

# Manual winding is a separate operation. The crown, winding transmission and
# ratchet move here while the sliding pinion stays engaged in winding position.
winding = [
    wheel_track("stem",18,-.22,0,lambda t: t*90,axis="X",seconds=4),
    wheel_track("sliding_pinion",13.58,.1,0,lambda t: t*90,axis="X",seconds=4),
    wheel_track("winding_pinion",15.36,.1,0,lambda t: t*90,axis="X",seconds=4),
    wheel_track("crown_wheel",10.4,-3.88,-.05,lambda t: t*30,seconds=4),
    wheel_track("ratchet_wheel",4.45,-3.98,-8.2,lambda t: t*-20,seconds=4),
]
anim.sequence("manual_winding",winding,ease="linear")
anim.camera_clip("manual_winding",dict(view="rear",parts=["caseback","crown"],padding=1.2))
cover=joints.slider([objects["bezel"],objects["front_crystal"],objects["front_gasket"]],"-Y",
                    limits=(0,.022),name="front_layer_display")
dial=joints.slider([objects["chapter_ring"]],"-Y",limits=(0,.010),name="chapter_ring_display")
guide=anim.guide(title="How it works")
photos=[dict(source="tissot-front.png",locator="Factory front view")]
material_note=[dict(source="PLAN.md",locator="Display poses and escapement scope")]
guide.step("overview","Read the hours and minutes at the center and the small seconds at nine.",
           seconds=2.6,hold=.8,evidence=photos,camera=dict(view="isometric",azimuth=19,elevation=11,padding=1.18))
guide.step("sapphire","Lift the front glazing in this display to reveal the open dial.",
           {cover:.022},seconds=2.4,hold=.6,evidence=material_note,
           camera=dict(view="front",azimuth=41,elevation=13,padding=1.15))
guide.step("chapter_ring","Separate the chapter ring to expose the movement perimeter.",
           {dial:.010},seconds=2.4,hold=.6,evidence=material_note,
           camera=dict(view="front",azimuth=35,elevation=11,parts=["case_middle","chapter_ring"],padding=1.42))
guide.step("energy","Follow the mainspring barrel through the wheel train to the small-seconds pivot.",
           seconds=2.2,hold=1.1,evidence=material_note,
           camera=dict(view="front",azimuth=-21,elevation=-10,parts=["barrel","center_wheel","fourth_wheel"],padding=1.5))
guide.step("regulation","The pallet fork meters the escape wheel. The balance and hairspring set the rhythm.",
           {b_joint:39,p_joint:10},seconds=1.7,hold=.4,evidence=material_note,
           camera=dict(view="front",azimuth=-25,elevation=12,parts=["balance","pallet_fork","escape_wheel"],padding=1.56))
guide.step("return_regulator","Return the regulating parts to their display position.",
           {b_joint:0,p_joint:0},seconds=1.1,hold=.2,evidence=material_note)
guide.step("restore_dial","Return the chapter ring to the case.",{dial:0},seconds=1.9,hold=.3,evidence=material_note,
           camera=dict(view="front",azimuth=37,elevation=12,padding=1.25))
guide.step("restore_glass","Reassemble the front glazing and return to the watch.",
           {cover:0},seconds=2.3,hold=.8,evidence=material_note,
           camera=dict(view="isometric",azimuth=21,elevation=11,padding=1.18))
guide.finish()

def write(name,payload):
    (OUT/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")

write("parts.json",dict(schemaVersion=1,units="metres",coordinateSystem="glTF-Y-up",product=PRODUCT,
                        assemblies=[dict(id=key,label=label,purpose=purpose) for key,(label,purpose) in families.items()],
                        parts=parts))
write("explorer.json",dict(schemaVersion=1,
      notice="Illustrative display separation. Squelette geometry is photo-based and ETA movement interfaces are estimated.",groups=groups))
# Declare only modeled fitted contacts with a specific attachment.
for child, parent, reason in [
    ("bezel","case_middle","Bezel flange seats in the case recess."),
    ("upper_lugs","case_middle","Upper lug pair is integral to the case middle."),
    ("lower_lugs","case_middle","Lower lug pair is integral to the case middle."),
    ("upper_bar","upper_lugs","Spring-bar ends engage the upper lug bores."),
    ("lower_bar","lower_lugs","Spring-bar ends engage the lower lug bores."),
    ("upper_bar","upper_strap","The spring bar passes through the strap end."),
    ("lower_bar","lower_strap","The spring bar passes through the strap end."),
    ("crown","stem","Stem fits the axial crown socket."),
    ("crown","crown_inset","Crown inlay seats in the end cap."),
    ("hand_cap","minute_hand","The cap sits on the minute-hand collet."),
    ("pallet_1","pallet_fork","The entry stone is fixed to the fork."),
    ("pallet_2","pallet_fork","The exit stone is fixed to the fork."),
]:
    core.allow_contact(objects[child],objects[parent],reason)
core.finish(str(OUT/"model.blend"))
