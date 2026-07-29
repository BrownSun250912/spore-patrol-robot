
import tkinter as tk
from tkinter import ttk 
from tkinter import filedialog 
from tkinter import messagebox 
from tkinter import simpledialog 
import math 
import csv 
import json 
import random 
import os 
import sys 
from datetime import datetime 
import sqlite3 
try :
    from PIL import Image 
    from PIL import ImageTk 
    from PIL import ImageDraw 
    HAS_PILLOW =True 
except ImportError :
    HAS_PILLOW =False 
def rotate_point (point_x ,point_y ,center_x ,center_y ,theta_radians ):
    dx =point_x -center_x 
    dy =point_y -center_y 
    cos_theta =math .cos (theta_radians )
    sin_theta =math .sin (theta_radians )
    new_x =dx *cos_theta -dy *sin_theta +center_x 
    new_y =dx *sin_theta +dy *cos_theta +center_y 
    return new_x ,new_y 
def point_in_polygon (px ,py ,polygon_vertices ):
    inside =False 
    j =len (polygon_vertices )-1 
    for i in range (len (polygon_vertices )):
        xi ,yi =polygon_vertices [i ]
        xj ,yj =polygon_vertices [j ]
        if ((yi >py )!=(yj >py ))and (px <(xj -xi )*(py -yi )/(yj -yi )+xi ):
            inside =not inside 
        j =i 
    return inside 
def scanline_intersections (scan_y ,polygon_vertices ):
    intersections =[]
    j =len (polygon_vertices )-1 
    for i in range (len (polygon_vertices )):
        px1 ,py1 =polygon_vertices [i ]
        px2 ,py2 =polygon_vertices [j ]
        if (py1 <=scan_y <py2 )or (py2 <=scan_y <py1 ):
            if abs (py2 -py1 )>1e-9 :
                intersect_x =px1 +(scan_y -py1 )*(px2 -px1 )/(py2 -py1 )
                intersections .append (intersect_x )
        j =i 
    intersections .sort ()
    return intersections 
def polygon_area (polygon_vertices ):
    area_sum =0.0 
    j =len (polygon_vertices )-1 
    for i in range (len (polygon_vertices )):
        area_sum +=polygon_vertices [i ][0 ]*polygon_vertices [j ][1 ]
        area_sum -=polygon_vertices [j ][0 ]*polygon_vertices [i ][1 ]
        j =i 
    return abs (area_sum )/2.0 
def polygon_centroid (polygon_vertices ):
    cx_sum =0.0 
    cy_sum =0.0 
    j =len (polygon_vertices )-1 
    for i in range (len (polygon_vertices )):
        xi ,yi =polygon_vertices [i ]
        xj ,yj =polygon_vertices [j ]
        cross =xi *yj -xj *yi 
        cx_sum +=(xi +xj )*cross 
        cy_sum +=(yi +yj )*cross 
        j =i 
    area_times_6 =6.0 *polygon_area (polygon_vertices )
    if area_times_6 ==0 :
        return (polygon_vertices [0 ][0 ],polygon_vertices [0 ][1 ])
    return (cx_sum /area_times_6 ,cy_sum /area_times_6 )
def distance_between (point_a ,point_b ):
    return math .hypot (point_a [0 ]-point_b [0 ],point_a [1 ]-point_b [1 ])
def bounding_box (points_list ):
    xs =[p [0 ]for p in points_list ]
    ys =[p [1 ]for p in points_list ]
    return min (xs ),max (xs ),min (ys ),max (ys )
def confidence_to_rgba (confidence_value ):
    if confidence_value <0.001 :
        return (0 ,0 ,0 ,0 )
    if confidence_value <0.25 :
        t =confidence_value /0.25 
        red =220 
        green =int (30 +80 *t )
        blue =30 
    elif confidence_value <0.5 :
        t =(confidence_value -0.25 )/0.25 
        red =220 
        green =int (110 +100 *t )
        blue =30 
    elif confidence_value <0.75 :
        t =(confidence_value -0.5 )/0.25 
        red =int (220 -150 *t )
        green =int (210 +40 *t )
        blue =30 
    else :
        t =(confidence_value -0.75 )/0.25 
        red =int (70 -30 *t )
        green =int (250 -50 *t )
        blue =30 
    alpha =int (50 +110 *confidence_value )
    return (red ,green ,blue ,alpha )

class CoverageEvaluator :
    def __init__ (self ,evaluation_grid ,candidate_pool ,effective_radius_px ):
        self .evaluation_grid =evaluation_grid 
        self .candidate_pool =candidate_pool 
        self .radius_squared =effective_radius_px **2 
        self .cell_size =max (effective_radius_px ,20.0 )
        self .grid_bins ={}
        for grid_index ,(gx ,gy )in enumerate (evaluation_grid ):
            bin_key =(int (gx /self .cell_size ),int (gy /self .cell_size ))
            if bin_key not in self .grid_bins :
                self .grid_bins [bin_key ]=[]
            self .grid_bins [bin_key ].append (grid_index )
    def _query_nearby_grid_indices (self ,center_x ,center_y ):
        bin_x =int (center_x /self .cell_size )
        bin_y =int (center_y /self .cell_size )
        result_indices =[]
        for dx in (-1 ,0 ,1 ):
            for dy in (-1 ,0 ,1 ):
                key =(bin_x +dx ,bin_y +dy )
                if key in self .grid_bins :
                    result_indices .extend (self .grid_bins [key ])
        return result_indices 
    def evaluate_candidate_gain (self ,candidate ,base_confidence ):
        center_x ,center_y =candidate ['real_xy']
        total_gain =0.0 
        new_confidence =list (base_confidence )
        nearby_indices =self ._query_nearby_grid_indices (center_x ,center_y )
        for grid_index in nearby_indices :
            gx ,gy =self .evaluation_grid [grid_index ]
            dx =gx -center_x 
            dy =gy -center_y 
            dist_sq =dx *dx +dy *dy 
            if dist_sq <self .radius_squared :
                coverage_value =1.0 -dist_sq /self .radius_squared 
                if coverage_value >base_confidence [grid_index ]:
                    delta_gain =coverage_value -base_confidence [grid_index ]
                    total_gain +=delta_gain 
                    new_confidence [grid_index ]=coverage_value 
        return total_gain ,new_confidence 
    def greedy_select (self ,base_confidence ,num_to_select ,progress_callback =None ):
        selected_candidates =[]
        current_confidence =list (base_confidence )
        available_flags =[True ]*len (self .candidate_pool )
        for step in range (num_to_select ):
            best_candidate =None 
            best_gain =-1.0 
            best_new_confidence =None 
            best_candidate_index =-1 
            for cand_index ,candidate in enumerate (self .candidate_pool ):
                if not available_flags [cand_index ]:
                    continue 
                gain ,new_conf =self .evaluate_candidate_gain (
                candidate ,current_confidence )
                if gain >best_gain :
                    best_gain =gain 
                    best_candidate =candidate 
                    best_new_confidence =new_conf 
                    best_candidate_index =cand_index 
            if best_candidate is None or best_gain <0.001 :
                break 
            selected_candidates .append (best_candidate )
            current_confidence =best_new_confidence 
            available_flags [best_candidate_index ]=False 
            if progress_callback :
                progress_callback (step +1 ,num_to_select )
        return selected_candidates ,current_confidence 
def compute_headland_path (node_a ,node_b ,ridge_database ,
rotation_center_x ,rotation_center_y ,
rotation_theta ):
    ridge_a =node_a ['ridge_idx']
    ridge_b =node_b ['ridge_idx']
    xa_rot ,ya_rot =node_a ['rot_xy']
    xb_rot ,yb_rot =node_b ['rot_xy']
    if ridge_a ==ridge_b :
        distance =abs (xa_rot -xb_rot )
        waypoints =[node_a ['real_xy'],node_b ['real_xy']]
        return distance ,waypoints 
    left_a =ridge_database [ridge_a ]['left_rot']
    left_b =ridge_database [ridge_b ]['left_rot']
    right_a =ridge_database [ridge_a ]['right_rot']
    right_b =ridge_database [ridge_b ]['right_rot']
    distance_left =(xa_rot -left_a )+abs (ya_rot -yb_rot )+(xb_rot -left_b )
    distance_right =(right_a -xa_rot )+abs (ya_rot -yb_rot )+(right_b -xb_rot )
    if distance_left <distance_right :
        waypoints =[
        node_a ['real_xy'],
        rotate_point (left_a ,ya_rot ,rotation_center_x ,rotation_center_y ,rotation_theta ),
        rotate_point (left_b ,yb_rot ,rotation_center_x ,rotation_center_y ,rotation_theta ),
        node_b ['real_xy']
        ]
        return distance_left ,waypoints 
    else :
        waypoints =[
        node_a ['real_xy'],
        rotate_point (right_a ,ya_rot ,rotation_center_x ,rotation_center_y ,rotation_theta ),
        rotate_point (right_b ,yb_rot ,rotation_center_x ,rotation_center_y ,rotation_theta ),
        node_b ['real_xy']
        ]
        return distance_right ,waypoints 
def nearest_neighbor_tour (nodes_list ,ridge_database ,
rotation_center_x ,rotation_center_y ,
rotation_theta ):
    num_nodes =len (nodes_list )
    if num_nodes <=2 :
        return list (range (num_nodes ))
    visited =[False ]*num_nodes 
    tour =[0 ]
    visited [0 ]=True 
    for _ in range (num_nodes -1 ):
        last_visited =tour [-1 ]
        best_next =-1 
        best_distance =float ('inf')
        for j in range (num_nodes ):
            if visited [j ]:
                continue 
            dist ,_ =compute_headland_path (
            nodes_list [last_visited ],nodes_list [j ],
            ridge_database ,rotation_center_x ,rotation_center_y ,rotation_theta )
            if dist <best_distance :
                best_distance =dist 
                best_next =j 
        tour .append (best_next )
        visited [best_next ]=True 
    return tour 
def two_opt_improve (initial_tour ,nodes_list ,ridge_database ,
rotation_center_x ,rotation_center_y ,
rotation_theta ,max_iterations =50 ):
    num_nodes =len (nodes_list )
    if num_nodes <3 :
        return initial_tour 
    best_tour =list (initial_tour )
    improved =True 
    iteration_count =0 
    while improved and iteration_count <max_iterations :
        improved =False 
        iteration_count +=1 
        for i in range (1 ,num_nodes -2 ):
            for j in range (i +1 ,num_nodes ):
                if j -i ==1 :
                    continue 
                a_idx ,b_idx =best_tour [i -1 ],best_tour [i ]
                c_idx ,d_idx =best_tour [j ],best_tour [(j +1 )%num_nodes ]
                dist_ab ,_ =compute_headland_path (
                nodes_list [a_idx ],nodes_list [b_idx ],
                ridge_database ,rotation_center_x ,rotation_center_y ,rotation_theta )
                dist_cd ,_ =compute_headland_path (
                nodes_list [c_idx ],nodes_list [d_idx ],
                ridge_database ,rotation_center_x ,rotation_center_y ,rotation_theta )
                dist_ac ,_ =compute_headland_path (
                nodes_list [a_idx ],nodes_list [c_idx ],
                ridge_database ,rotation_center_x ,rotation_center_y ,rotation_theta )
                dist_bd ,_ =compute_headland_path (
                nodes_list [b_idx ],nodes_list [d_idx ],
                ridge_database ,rotation_center_x ,rotation_center_y ,rotation_theta )
                if (dist_ac +dist_bd )<(dist_ab +dist_cd ):
                    best_tour [i :j +1 ]=reversed (best_tour [i :j +1 ])
                    improved =True 
    return best_tour 
PARAMETER_PRESETS ={
"小麦试验田(小)":{
"ref":"50.0","ridge":"2.5","samp":"6",
"r":"15.0","K":"2","spd":"0.4"
},
"玉米大田(中)":{
"ref":"100.0","ridge":"4.0","samp":"8",
"r":"20.0","K":"2","spd":"0.5"
},
"水稻连片(大)":{
"ref":"200.0","ridge":"3.0","samp":"12",
"r":"25.0","K":"3","spd":"0.6"
},
"果园稀疏(宽垄)":{
"ref":"80.0","ridge":"5.0","samp":"5",
"r":"30.0","K":"1","spd":"0.4"
},
"菜地密植(窄垄)":{
"ref":"60.0","ridge":"1.5","samp":"10",
"r":"12.0","K":"2","spd":"0.3"
},
}

class InspectionSystem :
    def __init__ (self ,root_window ):
        self .root =root_window 
        self .root .title ("多模态智能巡检系统 V3.0")
        self .root .geometry ("1400x850")
        self .root .protocol ("WM_DELETE_WINDOW",self ._on_window_close )
        self .color_background ="#161a1d"
        self .color_panel ="#212529"
        self .color_card ="#2c313c"
        self .color_accent ="#00ecc6"
        self .color_alert ="#e1b12c"
        self .color_danger ="#e74c3c"
        self .color_info ="#00a8ff"
        self .color_safe ="#27ae60"
        self .color_ridge ="#282e38"
        self .color_text ="#dcdde1"
        self .color_dim ="#718093"
        self .round_colors =[
        "#ff9f43","#00a8ff","#e056a0","#f1c40f","#9b59b6"
        ]
        self .risk_colors ={
        'low':self .color_safe ,
        'medium':self .color_alert ,
        'high':self .color_danger ,
        'pending':self .color_dim 
        }
        self .pil_image =None 
        self .tk_photo_image =None 
        self .field_polygon =[]
        self .field_polygon_meters =[]
        self .scale_px_per_meter =1.0 
        self .reference_x_px =0.0 
        self .reference_y_px =0.0 
        self .spore_radius_meters =20.0 
        self .vehicle_speed_ms =0.5 
        self .ridge_database ={}
        self .round_nodes_list =[]
        self .round_tours =[]
        self .round_segments =[]
        self .cumulative_confidence =[]
        self .evaluation_grid =[]
        self .grid_step_px =1.0 
        self .sampling_points =[]
        self .is_drawing_polygon =False 
        self .selected_point_index =-1 
        self .coverage_radius_meters =20.0
        self .show_grid =True
        self .show_legend =True
        self .undo_stack =[]
        self .heatmap_photo =None
        self .circles_photo =None
        self .confidence_photo =None
        self .legend_photo =None
        self .image_offset_x =0
        self .image_offset_y =0
        self .canvas_width =1000
        self .canvas_height =800
        self .zoom_scale =1.0
        self .pan_x =0.0
        self .pan_y =0.0
        self .is_dragging =False
        self .drag_start_x =0
        self .drag_start_y =0
        self .root .bind ('<Control-z>',lambda event :self ._undo_vertex ())
        self .root .bind ('<Control-s>',lambda event :self .export_json ())
        self .db_path =os .path .join (os .path .dirname (os .path .abspath (__file__ )),"inspection_history.db")
        self ._db_init ()
        self ._build_interface ()
    def _db_init (self ):
        try :
            self .conn =sqlite3 .connect (self .db_path )
            cursor =self .conn .cursor ()
            cursor .execute ("""
                CREATE TABLE IF NOT EXISTS fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    area_m2 REAL,
                    polygon_json TEXT,
                    scale REAL,
                    ref_x REAL,
                    ref_y REAL,
                    created_at TEXT
                )
            """)
            cursor .execute ("""
                CREATE TABLE IF NOT EXISTS sampling_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    field_id INTEGER,
                    point_id TEXT,
                    real_x REAL,
                    real_y REAL,
                    x_m REAL,
                    y_m REAL,
                    ridge_idx INTEGER,
                    round_idx INTEGER,
                    turbidity REAL,
                    risk TEXT,
                    read_time TEXT,
                    pcr_ct REAL,
                    pcr_conc REAL,
                    pcr_qual TEXT,
                    pcr_gene TEXT,
                    pcr_verdict TEXT,
                    pcr_is_simulated INTEGER,
                    FOREIGN KEY(field_id) REFERENCES fields(id) ON DELETE CASCADE
                )
            """)
            cursor .execute ("""
                CREATE TABLE IF NOT EXISTS std_curves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    field_id INTEGER,
                    gene TEXT,
                    slope REAL,
                    intercept REAL,
                    r_square REAL,
                    FOREIGN KEY(field_id) REFERENCES fields(id) ON DELETE CASCADE
                )
            """)
            self .conn .commit ()
        except Exception as e :
            messagebox .showerror ("数据库错误",f"数据库初始化失败: {e}")
    def _db_save_field (self ):
        if not self .field_polygon :
            messagebox .showwarning ("保存失败","请先在地图上绘制并闭合地块边界。");return 
        field_name =simpledialog .askstring ("保存地块","请输入保存的地块项目名称:",parent =self .root )
        if not field_name :
            return 
        field_name =field_name .strip ()
        if not field_name :
            return 
        try :
            cursor =self .conn .cursor ()
            cursor .execute ("SELECT id FROM fields WHERE name=?",(field_name ,))
            row =cursor .fetchone ()
            if row :
                if not messagebox .askyesno ("覆盖确认",f"已存在名称为 '{field_name}' 的地块项目。是否覆盖保存？"):
                    return 
                field_id =row [0 ]
                cursor .execute ("""
                    UPDATE fields SET area_m2=?, polygon_json=?, scale=?, ref_x=?, ref_y=?, created_at=? WHERE id=?
                """,(
                polygon_area (self .field_polygon )/(self .scale_px_per_meter **2 )if self .scale_px_per_meter >0 else 0 ,
                json .dumps (self .field_polygon ),
                self .scale_px_per_meter ,
                self .reference_x_px ,
                self .reference_y_px ,
                datetime .now ().strftime ('%Y-%m-%d %H:%M:%S'),
                field_id 
                ))
            else :
                cursor .execute ("""
                    INSERT INTO fields (name, area_m2, polygon_json, scale, ref_x, ref_y, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,(
                field_name ,
                polygon_area (self .field_polygon )/(self .scale_px_per_meter **2 )if self .scale_px_per_meter >0 else 0 ,
                json .dumps (self .field_polygon ),
                self .scale_px_per_meter ,
                self .reference_x_px ,
                self .reference_y_px ,
                datetime .now ().strftime ('%Y-%m-%d %H:%M:%S')
                ))
                field_id =cursor .lastrowid 
            cursor .execute ("DELETE FROM sampling_points WHERE field_id=?",(field_id ,))
            for pt in self .sampling_points :
                cursor .execute ("""
                    INSERT INTO sampling_points 
                    (field_id, point_id, real_x, real_y, x_m, y_m, ridge_idx, round_idx, turbidity, risk, read_time,
                     pcr_ct, pcr_conc, pcr_qual, pcr_gene, pcr_verdict, pcr_is_simulated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,(
                field_id ,
                pt .get ('point_id',''),
                pt .get ('real_xy',(0 ,0 ))[0 ],
                pt .get ('real_xy',(0 ,0 ))[1 ],
                pt .get ('x_m',0.0 ),
                pt .get ('y_m',0.0 ),
                pt .get ('ridge_idx',0 ),
                pt .get ('round',0 ),
                pt .get ('turbidity'),
                pt .get ('risk','pending'),
                pt .get ('read_time',''),
                pt .get ('pcr_ct'),
                pt .get ('pcr_conc'),
                pt .get ('pcr_qual',''),
                pt .get ('pcr_gene',''),
                pt .get ('pcr_verdict',''),
                1 if pt .get ('pcr_is_simulated',False )else 0 
                ))
            cursor .execute ("DELETE FROM std_curves WHERE field_id=?",(field_id ,))
            cursor .execute ("""
                INSERT INTO std_curves (field_id, gene, slope, intercept, r_square)
                VALUES (?, ?, ?, ?, ?)
            """,(
            field_id ,
            self .pcr_target_gene ,
            self .pcr_slope ,
            self .pcr_intercept ,
            0.99 
            ))
            self .conn .commit ()
            self ._db_refresh_combo ()
            self .db_field_var .set (field_name )
            self .status_variable .set (f"DB SAVED: 地块 '{field_name}' 保存成功！")
        except Exception as e :
            messagebox .showerror ("保存错误",f"地块项目写入数据库异常: {e}")
    def _db_load_field (self ,event =None ):
        field_name =self .db_field_var .get ()
        if not field_name :
            return 
        try :
            cursor =self .conn .cursor ()
            cursor .execute ("SELECT id, polygon_json, scale, ref_x, ref_y FROM fields WHERE name=?",(field_name ,))
            row =cursor .fetchone ()
            if not row :
                messagebox .showerror ("加载错误",f"未找到名为 '{field_name}' 的地块项目。");return 
            field_id ,poly_json ,scale ,ref_x ,ref_y =row 
            self .field_polygon =json .loads (poly_json )
            self .scale_px_per_meter =scale 
            self .reference_x_px =ref_x 
            self .reference_y_px =ref_y 
            cursor .execute ("""
                SELECT point_id, real_x, real_y, x_m, y_m, ridge_idx, round_idx, turbidity, risk, read_time,
                       pcr_ct, pcr_conc, pcr_qual, pcr_gene, pcr_verdict, pcr_is_simulated
                FROM sampling_points WHERE field_id=? ORDER BY id ASC
            """,(field_id ,))
            rows =cursor .fetchall ()
            self .sampling_points =[]
            for r in rows :
                pt ={
                'point_id':r [0 ],
                'real_xy':(r [1 ],r [2 ]),
                'x_m':r [3 ],
                'y_m':r [4 ],
                'ridge_idx':r [5 ],
                'round':r [6 ],
                'turbidity':r [7 ],
                'risk':r [8 ]or 'pending',
                'read_time':r [9 ]or '',
                'pcr_ct':r [10 ],
                'pcr_conc':r [11 ],
                'pcr_qual':r [12 ]or '',
                'pcr_gene':r [13 ]or '',
                'pcr_verdict':r [14 ]or '',
                'pcr_is_simulated':bool (r [15 ])
                }
                self .sampling_points .append (pt )
            self ._redraw_current_view ()
            self .status_variable .set (f"DB LOADED: 已载入历史地块 '{field_name}'，包含 {len(self.sampling_points)} 个采样点。")
        except Exception as e :
            messagebox .showerror ("加载错误",f"从数据库读取数据失败: {e}")
    def _db_delete_field (self ):
        field_name =self .db_field_var .get ()
        if not field_name :
            messagebox .showwarning ("删除失败","请先选择需要删除的历史地块项目。");return 
        if not messagebox .askyesno ("删除确认",f"确定要永久删除地块项目 '{field_name}' 吗？此操作不可恢复。"):
            return 
        try :
            cursor =self .conn .cursor ()
            cursor .execute ("DELETE FROM fields WHERE name=?",(field_name ,))
            self .conn .commit ()
            self ._db_refresh_combo ()
            self .status_variable .set (f"DB DELETED: 地块 '{field_name}' 已成功从数据库中移除。")
        except Exception as e :
            messagebox .showerror ("删除错误",f"数据库删除失败: {e}")
    def _db_refresh_combo (self ):
        try :
            cursor =self .conn .cursor ()
            cursor .execute ("SELECT name FROM fields ORDER BY id DESC")
            names =[r [0 ]for r in cursor .fetchall ()]
            self .db_field_combo ['values']=names 
            if names :
                self .db_field_combo .current (0 )
            else :
                self .db_field_var .set ("")
        except Exception as e :
            print (f"Failed to refresh DB combo: {e}")
    def _build_interface (self ):
        style =ttk .Style ()
        style .theme_use ('clam')
        style .configure ("TLabel",foreground =self .color_text ,
        background =self .color_panel )
        style .configure ("TNotebook",background =self .color_panel ,borderwidth =0 )
        style .configure ("TNotebook.Tab",padding =[14 ,4 ],font =("微软雅黑",10 ))
        right_frame =tk .Frame (self .root ,bg =self .color_background )
        right_frame .pack (side ="right",fill ="both",expand =True )
        self .main_canvas =tk .Canvas (
        right_frame ,bg =self .color_background ,highlightthickness =0 )
        self .main_canvas .pack (fill ="both",expand =True )
        self .main_canvas .bind ("<Motion>",self ._on_canvas_mouse_move )
        self .coordinate_label =tk .Label (
        right_frame ,text ="",fg =self .color_dim ,
        bg =self .color_background ,font =("Consolas",9 ))
        self .coordinate_label .place (x =8 ,y =8 )
        self .status_variable =tk .StringVar ()
        self .status_variable .set (
        "SYS READY: 导入卫星图 → 标定边界 → 规划路径 → 导出方案")
        tk .Label (right_frame ,textvariable =self .status_variable ,
        fg =self .color_alert ,bg =self .color_background ,
        font =("微软雅黑",10 ,"bold")).pack (side ="bottom",pady =6 )
        self .planning_panel =tk .Frame (
        self .root ,bg =self .color_panel ,width =360 )
        self .planning_panel .pack (side ="left",fill ="y")
        self .planning_panel .pack_propagate (False )
        self ._build_planning_tab ()
        self .main_canvas .bind ("<Button-1>",self ._on_canvas_left_click )
        self .main_canvas .bind ("<ButtonPress-3>",self ._on_canvas_pan_start )
        self .main_canvas .bind ("<B3-Motion>",self ._on_canvas_pan_drag )
        self .main_canvas .bind ("<ButtonRelease-3>",self ._on_canvas_pan_end )
        self .main_canvas .bind ("<MouseWheel>",self ._on_canvas_zoom )
        self .main_canvas .bind ("<Button-4>",lambda e :self ._on_canvas_zoom (e ,1.15 ))
        self .main_canvas .bind ("<Button-5>",lambda e :self ._on_canvas_zoom (e ,0.85 ))
        self .main_canvas .bind ("<Configure>",lambda event :self ._redraw_current_view ())
    def _make_scrollable_panel (self ,parent_frame ):
        scroll_canvas =tk .Canvas (
        parent_frame ,bg =self .color_panel ,highlightthickness =0 ,width =360 )
        scrollbar =ttk .Scrollbar (
        parent_frame ,orient ="vertical",command =scroll_canvas .yview )
        inner_frame =tk .Frame (scroll_canvas ,bg =self .color_panel )
        inner_frame .bind (
        "<Configure>",
        lambda event :scroll_canvas .configure (
        scrollregion =scroll_canvas .bbox ("all")))
        scroll_canvas .create_window (
        (0 ,0 ),window =inner_frame ,anchor ="nw",width =344 )
        scroll_canvas .configure (yscrollcommand =scrollbar .set )
        scroll_canvas .pack (side ="left",fill ="both",expand =True )
        scrollbar .pack (side ="right",fill ="y")
        def on_mouse_wheel (event ):
            scroll_canvas .yview_scroll (
            int (-1 *(event .delta /120 )),"units")
        scroll_canvas .bind (
        "<Enter>",lambda e :scroll_canvas .bind_all ("<MouseWheel>",on_mouse_wheel ))
        scroll_canvas .bind (
        "<Leave>",lambda e :scroll_canvas .unbind_all ("<MouseWheel>"))
        return inner_frame 
    def _build_planning_tab (self ):
        tab =self .planning_panel
        tab .pack_propagate (False )
        inner =self ._make_scrollable_panel (tab )
        def add_button (button_text ,command ,padding_y =8 ):
            tk .Button (
            inner ,text =button_text ,
            bg =self .color_card ,fg =self .color_text ,bd =0 ,
            padx =15 ,pady =4 ,cursor ="hand2",
            font =("微软雅黑",10 ),command =command 
            ).pack (pady =padding_y ,fill ="x",padx =14 )
        tk .Label (
        inner ,text ="PATH PLANNING CONTROL",
        fg =self .color_dim ,bg =self .color_panel ,
        font =("Consolas",9 ,"bold")
        ).pack (pady =(10 ,2 ))
        db_frame =tk .Frame (inner ,bg =self .color_card ,bd =1 ,relief ="solid")
        db_frame .pack (pady =8 ,fill ="x",padx =14 )
        tk .Label (
        db_frame ,text ="历史巡检地块数据库",
        fg =self .color_info ,bg =self .color_card ,
        font =("微软雅黑",10 ,"bold")
        ).pack (pady =(6 ,2 ))
        self .db_field_var =tk .StringVar ()
        self .db_field_combo =ttk .Combobox (
        db_frame ,textvariable =self .db_field_var ,state ="readonly",font =("微软雅黑",9 ))
        self .db_field_combo .pack (pady =4 ,fill ="x",padx =10 )
        self .db_field_combo .bind ("<<ComboboxSelected>>",self ._db_load_field )
        db_btn_frame =tk .Frame (db_frame ,bg =self .color_card )
        db_btn_frame .pack (pady =(2 ,6 ),fill ="x",padx =10 )
        tk .Button (
        db_btn_frame ,text ="保存当前项目",bg =self .color_info ,fg ="white",bd =0 ,
        padx =8 ,pady =3 ,font =("微软雅黑",9 ),cursor ="hand2",
        command =self ._db_save_field 
        ).pack (side ="left",padx =2 ,fill ="x",expand =True )
        tk .Button (
        db_btn_frame ,text ="删除选中项目",bg =self .color_danger ,fg ="white",bd =0 ,
        padx =8 ,pady =3 ,font =("微软雅黑",9 ),cursor ="hand2",
        command =self ._db_delete_field 
        ).pack (side ="left",padx =2 ,fill ="x",expand =True )
        self ._db_refresh_combo ()
        add_button ("1. 导入空地多光谱卫星图",self ._load_satellite_image ,8 )
        add_button ("底图适配检查",self ._check_image_fit ,2 )
        add_button ("2. 标定不规则边界 (首边为垄向)",self ._start_polygon_drawing ,6 )
        add_button ("闭合农田拓扑空间",self ._close_polygon ,2 )
        add_button ("撤销上一个顶点 (Ctrl+Z / 右键)",self ._undo_vertex ,2 )
        add_button ("复位地图显示视角",self ._reset_map_view ,2 )
        preset_frame =tk .Frame (
        inner ,bg =self .color_card ,bd =1 ,relief ="solid")
        preset_frame .pack (pady =8 ,fill ="x",padx =14 )
        tk .Label (
        preset_frame ,text ="参数预设",
        fg =self .color_info ,bg =self .color_card ,
        font =("微软雅黑",10 ,"bold")
        ).pack (pady =(6 ,2 ))
        self .preset_variable =tk .StringVar (value ="玉米大田(中)")
        self .preset_combobox =ttk .Combobox (
        preset_frame ,textvariable =self .preset_variable ,
        values =list (PARAMETER_PRESETS .keys ()),
        state ="readonly",width =20 )
        self .preset_combobox .pack (pady =3 )
        preset_button_row =tk .Frame (preset_frame ,bg =self .color_card )
        preset_button_row .pack (pady =(3 ,2 ))
        tk .Button (
        preset_button_row ,text ="应用",bg =self .color_info ,
        fg ="white",bd =0 ,padx =8 ,pady =2 ,
        font =("微软雅黑",9 ),command =self ._apply_preset 
        ).pack (side ="left",padx =3 )
        tk .Button (
        preset_button_row ,text ="保存",bg ="#5f6368",
        fg =self .color_text ,bd =0 ,padx =6 ,pady =2 ,
        font =("微软雅黑",9 ),command =self ._save_preset 
        ).pack (side ="left",padx =3 )
        tk .Button (
        preset_button_row ,text ="载入",bg ="#5f6368",
        fg =self .color_text ,bd =0 ,padx =6 ,pady =2 ,
        font =("微软雅黑",9 ),command =self ._load_presets_from_file 
        ).pack (side ="left",padx =3 )
        param_frame =tk .Frame (
        inner ,bg =self .color_card ,bd =1 ,relief ="solid")
        param_frame .pack (pady =8 ,fill ="x",padx =14 )
        tk .Label (
        param_frame ,text ="规划参数设定",
        fg =self .color_info ,bg =self .color_card ,
        font =("微软雅黑",10 ,"bold")
        ).pack (pady =(6 ,4 ))
        param_grid =tk .Frame (param_frame ,bg =self .color_card )
        param_grid .pack ()
        def make_param_entry (label_text ,default_value ,row_index ,unit_text =""):
            tk .Label (
            param_grid ,text =label_text ,
            fg =self .color_text ,bg =self .color_card ,
            font =("微软雅黑",9 )
            ).grid (row =row_index ,column =0 ,pady =3 ,padx =(10 ,4 ),sticky ="w")
            entry_widget =tk .Entry (
            param_grid ,width =7 ,bg =self .color_background ,
            fg =self .color_accent ,bd =0 ,
            insertbackground ="white",font =("Consolas",10 ,"bold"))
            entry_widget .insert (0 ,default_value )
            entry_widget .grid (row =row_index ,column =1 ,pady =3 ,padx =2 ,sticky ="e")
            if unit_text :
                tk .Label (
                param_grid ,text =unit_text ,
                fg =self .color_dim ,bg =self .color_card ,
                font =("微软雅黑",8 )
                ).grid (row =row_index ,column =2 ,pady =3 ,padx =(0 ,8 ),sticky ="w")
            return entry_widget 
        self .entry_ref_length =make_param_entry (
        "基准首边长度","100.0",0 ,"m")
        self .entry_ridge_distance =make_param_entry (
        "作物种植垄距","4.0",1 ,"m")
        self .entry_samples_per_round =make_param_entry (
        "每轮采样点数P","8",2 )
        self .entry_spore_radius =make_param_entry (
        "孢子有效半径R","20.0",3 ,"m")
        self .entry_num_rounds =make_param_entry (
        "采集轮次K","2",4 )
        self .entry_vehicle_speed =make_param_entry (
        "小车行驶速度","0.5",5 ,"m/s")
        checkbox_frame =tk .Frame (param_frame ,bg =self .color_card )
        checkbox_frame .pack (pady =(4 ,6 ))
        self .grid_checkbox_var =tk .BooleanVar (value =True )
        tk .Checkbutton (
        checkbox_frame ,text ="评估格网",variable =self .grid_checkbox_var ,
        fg =self .color_text ,bg =self .color_card ,
        selectcolor =self .color_background ,
        activebackground =self .color_card ,
        activeforeground =self .color_text ,
        font =("微软雅黑",9 ),command =self ._redraw_current_view 
        ).pack (side ="left",padx =6 )
        self .legend_checkbox_var =tk .BooleanVar (value =True )
        tk .Checkbutton (
        checkbox_frame ,text ="图例",variable =self .legend_checkbox_var ,
        fg =self .color_text ,bg =self .color_card ,
        selectcolor =self .color_background ,
        activebackground =self .color_card ,
        activeforeground =self .color_text ,
        font =("微软雅黑",9 ),command =self ._redraw_current_view 
        ).pack (side ="left",padx =6 )
        add_button ("推荐采样密度",self ._show_density_recommendation ,3 )
        add_button ("3. 求解全覆盖路由方案",self ._solve_planning_pipeline ,10 )
        add_button ("导出路径规划 JSON",self .export_json ,4 )
        add_button ("导出规划报告 TXT",self ._export_planning_report ,4 )
        add_button ("综合统计摘要",self ._show_statistics_window ,4 )
        add_button ("坐标验证",self ._validate_coordinates ,2 )
        add_button ("保存工作会话",self ._save_session ,2 )
        add_button ("恢复工作会话",self ._load_session ,2 )
        add_button ("一键批量导出 (JSON+CSV+TXT)",self ._batch_export_all ,4 )
        add_button ("清空画布",self ._clear_all_data ,4 )

    def _apply_preset (self ):
        preset_name =self .preset_variable .get ()
        if preset_name not in PARAMETER_PRESETS :
            return 
        preset_values =PARAMETER_PRESETS [preset_name ]
        mapping =[
        (self .entry_ref_length ,'ref'),
        (self .entry_ridge_distance ,'ridge'),
        (self .entry_samples_per_round ,'samp'),
        (self .entry_spore_radius ,'r'),
        (self .entry_num_rounds ,'K'),
        (self .entry_vehicle_speed ,'spd'),
        ]
        for entry_widget ,key in mapping :
            entry_widget .delete (0 ,"end")
            entry_widget .insert (0 ,preset_values [key ])
        self .status_variable .set (f"PRESET APPLIED: {preset_name}")
    def _save_preset (self ):
        preset_name =simpledialog .askstring (
        "保存预设","请输入预设名称:",parent =self .root )
        if not preset_name :
            return 
        new_preset ={
        "ref":self .entry_ref_length .get (),
        "ridge":self .entry_ridge_distance .get (),
        "samp":self .entry_samples_per_round .get (),
        "r":self .entry_spore_radius .get (),
        "K":self .entry_num_rounds .get (),
        "spd":self .entry_vehicle_speed .get (),
        }
        PARAMETER_PRESETS [preset_name ]=new_preset 
        self .preset_combobox ['values']=list (PARAMETER_PRESETS .keys ())
        self .preset_variable .set (preset_name )
        self .status_variable .set (f"PRESET SAVED: {preset_name}")
    def _load_presets_from_file (self ):
        file_path =filedialog .askopenfilename (
        filetypes =[("JSON 文件","*.json")],title ="载入预设文件")
        if not file_path :
            return 
        try :
            with open (file_path ,'r',encoding ='utf-8')as file_handle :
                loaded_data =json .load (file_handle )
        except Exception as error :
            messagebox .showerror ("载入失败",f"JSON 解析异常: {error}")
            return 
        added_count =0 
        for name ,values in loaded_data .items ():
            if isinstance (values ,dict )and all (
            k in values for k in ['ref','ridge','samp','r','K','spd']):
                PARAMETER_PRESETS [name ]=values 
                added_count +=1 
        if added_count >0 :
            self .preset_combobox ['values']=list (PARAMETER_PRESETS .keys ())
            self .status_variable .set (
            f"PRESETS LOADED: 从文件导入 {added_count} 个预设。")
        else :
            messagebox .showwarning (
            "载入失败","未找到合法的预设定义。")
    def _show_density_recommendation (self ):
        if not self .field_polygon or self .scale_px_per_meter <=0 :
            messagebox .showwarning ("提示","请先加载底图并标定多边形。")
            return 
        area_m2 =polygon_area (self .field_polygon )/(self .scale_px_per_meter **2 )
        coverage_per_point =math .pi *(self .spore_radius_meters **2 )
        recommended =max (3 ,int (area_m2 /coverage_per_point *1.3 ))
        messagebox .showinfo (
        "推荐采样密度",
        f"地块面积: {area_m2:.0f} m²\n"
        f"单点覆盖面积 (πR²): {coverage_per_point:.0f} m²\n"
        f"推荐每轮采样点数: ~{recommended} 点\n\n"
        f"提示: 狭长地块建议适当增加采样密度。")
    def _check_image_fit (self ):
        if not self .pil_image or not self .field_polygon :
            messagebox .showwarning ("提示","请先加载底图并标定多边形。")
            return 
        image_width ,image_height =self .pil_image .size 
        xs =[p [0 ]for p in self .field_polygon ]
        ys =[p [1 ]for p in self .field_polygon ]
        polygon_width =max (xs )-min (xs )
        polygon_height =max (ys )-min (ys )
        ratio_w =polygon_width /image_width *100 
        ratio_h =polygon_height /image_height *100 
        messagebox .showinfo (
        "底图适配检查",
        f"底图尺寸: {image_width}×{image_height} px\n"
        f"多边形范围: {polygon_width:.0f}×{polygon_height:.0f} px\n"
        f"占底图比例: {ratio_w:.0f}% × {ratio_h:.0f}%\n\n"
        f"{'比例合适' if 10 < ratio_w < 90 else '建议调整图片大小或重新标定'}")
    def _validate_coordinates (self ):
        if not self .field_polygon_meters :
            messagebox .showwarning ("验证","请先完成路径规划。")
            return 
        xs =[v [0 ]for v in self .field_polygon_meters ]
        ys =[v [1 ]for v in self .field_polygon_meters ]
        range_x =max (xs )-min (xs )
        range_y =max (ys )-min (ys )
        is_valid =0.5 <range_x <5000 and 0.5 <range_y <5000 
        messagebox .showinfo (
        "坐标验证",
        f"{'✓ 通过' if is_valid else '⚠ 异常'}\n"
        f"X 范围: [{min(xs):.1f}, {max(xs):.1f}] m\n"
        f"Y 范围: [{min(ys):.1f}, {max(ys):.1f}] m")
    def _risk_text (self ,risk_code ):
        mapping ={
        'low':'低风险','medium':'中风险',
        'high':'高风险','pending':'待检测'
        }
        return mapping .get (risk_code ,'待检测')
    def _on_canvas_mouse_move (self ,event ):
        img_x ,img_y =self .canvas_to_image (event .x ,event .y )
        if self .field_polygon :
            meter_x =(img_x -self .reference_x_px )/self .scale_px_per_meter if self .scale_px_per_meter >0 else 0
            meter_y =(img_y -self .reference_y_px )/self .scale_px_per_meter if self .scale_px_per_meter >0 else 0
            self .coordinate_label .config (
            text =f"px({int(img_x)},{int(img_y)})  m({meter_x:.1f},{meter_y:.1f})")
        else :
            self .coordinate_label .config (text ="")
    def _on_canvas_left_click (self ,event ):
        if not self .is_drawing_polygon :
            return 
        img_x ,img_y =self .canvas_to_image (event .x ,event .y )
        self .field_polygon .append ((img_x ,img_y ))
        self .undo_stack .append ((img_x ,img_y ))
        self .main_canvas .create_oval (
        event .x -3 ,event .y -3 ,event .x +3 ,event .y +3 ,
        fill ="#ffffff",outline =self .color_info ,width =1 )
        if len (self .field_polygon )>1 :
            prev_img_x ,prev_img_y =self .field_polygon [-2 ]
            prev_x ,prev_y =self .image_to_canvas (prev_img_x ,prev_img_y )
            color =self .color_info if len (
            self .field_polygon )==2 else "#ffffff"
            line_width =3 if len (self .field_polygon )==2 else 1.5 
            self .main_canvas .create_line (
            prev_x ,prev_y ,event .x ,event .y ,fill =color ,width =line_width )
    def _on_canvas_right_click (self ,event ):
        if self .is_drawing_polygon :
            self ._undo_vertex ()
    def _undo_vertex (self ):
        if not self .is_drawing_polygon or not self .field_polygon :
            return 
        self .field_polygon .pop ()
        if self .undo_stack :
            self .undo_stack .pop ()
        self ._draw_planning_view ()
        self .status_variable .set (
        f"DIGITIZING: 已标定 {len(self.field_polygon)} 个顶点，右键撤销。")

    def _update_canvas_dimensions (self ):
        canvas_width =self .main_canvas .winfo_width ()
        canvas_height =self .main_canvas .winfo_height ()
        if canvas_width <10 :
            canvas_width ,canvas_height =1000 ,800 
        self .canvas_width =canvas_width 
        self .canvas_height =canvas_height 
        if self .pil_image :
            image_width ,image_height =self .pil_image .size 
            self .image_offset_x =(canvas_width -image_width )//2 
            self .image_offset_y =(canvas_height -image_height )//2 
        else :
            self .image_offset_x =0 
            self .image_offset_y =0 
    def canvas_to_image (self ,cx ,cy ):
        x_scaled =(cx -self .pan_x )/self .zoom_scale 
        y_scaled =(cy -self .pan_y )/self .zoom_scale 
        return x_scaled -self .image_offset_x ,y_scaled -self .image_offset_y 
    def image_to_canvas (self ,ix ,iy ):
        canvas_x =(ix +self .image_offset_x )*self .zoom_scale +self .pan_x 
        canvas_y =(iy +self .image_offset_y )*self .zoom_scale +self .pan_y 
        return canvas_x ,canvas_y 
    def _on_canvas_zoom (self ,event ,factor =None ):
        if not self .pil_image :
            return 
        if factor is None :
            factor =1.15 if event .delta >0 else 0.85 
        new_scale =max (0.4 ,min (6.0 ,self .zoom_scale *factor ))
        if abs (new_scale -self .zoom_scale )<1e-5 :
            return 
        mx ,my =event .x ,event .y 
        self .pan_x =mx -(mx -self .pan_x )*(new_scale /self .zoom_scale )
        self .pan_y =my -(my -self .pan_y )*(new_scale /self .zoom_scale )
        self .zoom_scale =new_scale 
        self ._zoom_pan_in_progress =True 
        self ._redraw_current_view ()
        self ._zoom_pan_in_progress =False 
        self .status_variable .set (f"VIEW: 缩放比率 {int(self.zoom_scale * 100)}%")
    def _on_canvas_pan_start (self ,event ):
        self .drag_start_x =event .x 
        self .drag_start_y =event .y 
        self .pan_orig_x =self .pan_x 
        self .pan_orig_y =self .pan_y 
        self .has_dragged =False 
        self .is_dragging =True 
    def _on_canvas_pan_drag (self ,event ):
        if not self .is_dragging :
            return 
        dx =event .x -self .drag_start_x 
        dy =event .y -self .drag_start_y 
        if abs (dx )>3 or abs (dy )>3 :
            self .has_dragged =True 
        self .pan_x =self .pan_orig_x +dx 
        self .pan_y =self .pan_orig_y +dy 
        self ._zoom_pan_in_progress =True 
        self ._redraw_current_view ()
        self ._zoom_pan_in_progress =False 
    def _on_canvas_pan_end (self ,event ):
        self .is_dragging =False 
        if not self .has_dragged :
            self ._on_canvas_right_click (event )
    def _reset_map_view (self ):
        self .zoom_scale =1.0 
        self .pan_x =0.0 
        self .pan_y =0.0 
        self ._redraw_current_view ()
        self .status_variable .set ("VIEW RESET: 画布视图已恢复默认比例。")
    def _clear_heatmap_caches (self ):
        pass
    def _get_current_tk_image (self ):
        if not self .pil_image :
            return None 
        w ,h =self .pil_image .size 
        nw =max (1 ,int (w *self .zoom_scale ))
        nh =max (1 ,int (h *self .zoom_scale ))
        if not hasattr (self ,'_cached_zoom_scale')or self ._cached_zoom_scale !=self .zoom_scale or not hasattr (self ,'_cached_tk_image')or self ._cached_tk_image is None :
            resized =self .pil_image .resize ((nw ,nh ),Image .LANCZOS )
            self ._cached_tk_image =ImageTk .PhotoImage (resized )
            self ._cached_zoom_scale =self .zoom_scale 
        return self ._cached_tk_image 
    def _redraw_current_view (self ):
        self ._clear_heatmap_caches ()
        self ._update_canvas_dimensions ()
        self ._draw_planning_view ()
    def _draw_planning_view (self ):
        self .main_canvas .delete ("all")
        self .confidence_photo =None 
        self .circles_photo =None 
        self .legend_photo =None 
        canvas_w ,canvas_h =self .canvas_width ,self .canvas_height 
        tk_img =self ._get_current_tk_image ()
        if tk_img :
            cx ,cy =self .image_to_canvas (0 ,0 )
            self .main_canvas .create_image (
            cx ,cy ,anchor ="nw",image =tk_img )
        polygon =self .field_polygon 
        if self .show_grid and self .evaluation_grid and self .grid_checkbox_var .get ():
            for (gx ,gy )in self .evaluation_grid :
                gx_c ,gy_c =self .image_to_canvas (gx ,gy )
                half_step =(self .grid_step_px *self .zoom_scale )/2.0 
                self .main_canvas .create_rectangle (
                gx_c -half_step ,gy_c -half_step ,
                gx_c +half_step ,gy_c +half_step ,
                fill ="#1a2332",outline ="")
        if HAS_PILLOW and self .cumulative_confidence and self .evaluation_grid :
            self ._draw_confidence_heatmap (canvas_w ,canvas_h )
        if len (polygon )>=2 :
            num_segments =len (polygon )-1 if self .is_drawing_polygon else len (polygon )
            for i in range (num_segments ):
                x1 ,y1 =polygon [i ]
                x2 ,y2 =polygon [(i +1 )%len (polygon )]
                x1_c ,y1_c =self .image_to_canvas (x1 ,y1 )
                x2_c ,y2_c =self .image_to_canvas (x2 ,y2 )
                edge_color =self .color_info if i ==0 else "#ffffff"
                edge_width =3 if i ==0 else 1.5 
                self .main_canvas .create_line (
                x1_c ,y1_c ,x2_c ,y2_c ,fill =edge_color ,width =edge_width )
            for vx ,vy in polygon :
                vx_c ,vy_c =self .image_to_canvas (vx ,vy )
                self .main_canvas .create_oval (
                vx_c -3 ,vy_c -3 ,vx_c +3 ,vy_c +3 ,
                fill ="#ffffff",outline =self .color_info ,width =1 )
        if not self .round_nodes_list :
            if self .show_legend and self .legend_checkbox_var .get ():
                self ._draw_planning_legend (canvas_w ,canvas_h )
            return 
        rotation_theta =math .atan2 (
        polygon [1 ][1 ]-polygon [0 ][1 ],
        polygon [1 ][0 ]-polygon [0 ][0 ])
        cx ,cy =self .reference_x_px ,self .reference_y_px 
        for ridge_info in self .ridge_database .values ():
            y_rot =ridge_info ['y_rot']
            left_rot =ridge_info ['left_rot']
            right_rot =ridge_info ['right_rot']
            start_pt =rotate_point (
            left_rot ,y_rot ,cx ,cy ,rotation_theta )
            end_pt =rotate_point (
            right_rot ,y_rot ,cx ,cy ,rotation_theta )
            start_pt_c =self .image_to_canvas (start_pt [0 ],start_pt [1 ])
            end_pt_c =self .image_to_canvas (end_pt [0 ],end_pt [1 ])
            self .main_canvas .create_line (
            start_pt_c [0 ],start_pt_c [1 ],end_pt_c [0 ],end_pt_c [1 ],
            fill =self .color_ridge ,width =1 )
        if HAS_PILLOW :
            self ._draw_coverage_circles_planning (canvas_w ,canvas_h )
        for round_index ,(nodes ,tour )in enumerate (
        zip (self .round_nodes_list ,self .round_tours )):
            path_color =self .round_colors [round_index %5 ]
            num_nodes =len (nodes )
            if num_nodes <2 :
                continue 
            for idx in range (num_nodes ):
                node_a =nodes [tour [idx ]]
                node_b =nodes [tour [(idx +1 )%num_nodes ]]
                _ ,waypoints =compute_headland_path (
                node_a ,node_b ,self .ridge_database ,
                cx ,cy ,rotation_theta )
                for k in range (len (waypoints )-1 ):
                    wk_c =self .image_to_canvas (waypoints [k ][0 ],waypoints [k ][1 ])
                    wk1_c =self .image_to_canvas (waypoints [k +1 ][0 ],waypoints [k +1 ][1 ])
                    self .main_canvas .create_line (
                    wk_c [0 ],wk_c [1 ],wk1_c [0 ],wk1_c [1 ],
                    fill =path_color ,width =2 ,dash =(6 ,4 ))
                    self ._draw_path_arrow (
                    wk_c [0 ],wk_c [1 ],wk1_c [0 ],wk1_c [1 ],
                    path_color )
            for local_idx ,node in enumerate (nodes ):
                nx ,ny =node ['real_xy']
                nx_c ,ny_c =self .image_to_canvas (nx ,ny )
                self .main_canvas .create_oval (
                nx_c -7 ,ny_c -7 ,nx_c +7 ,ny_c +7 ,
                fill =self .color_background ,outline =path_color ,width =2 )
                self .main_canvas .create_oval (
                nx_c -2.5 ,ny_c -2.5 ,nx_c +2.5 ,ny_c +2.5 ,
                fill ="#ffffff",outline ="")
                label_text =f"R{round_index + 1}-P{local_idx + 1}"
                self .main_canvas .create_text (
                nx_c +11 ,ny_c -17 ,text =label_text ,
                fill =path_color ,font =("Consolas",7 ,"bold"),anchor ="w")
        if self .show_legend and self .legend_checkbox_var .get ():
            self ._draw_planning_legend (canvas_w ,canvas_h )
    def _draw_confidence_heatmap (self ,canvas_w ,canvas_h ):
        overlay =Image .new ("RGBA",(canvas_w ,canvas_h ),(0 ,0 ,0 ,0 ))
        draw_handle =ImageDraw .Draw (overlay )
        half_step =self .grid_step_px /2.0 
        for i ,(gx ,gy )in enumerate (self .evaluation_grid ):
            if i >=len (self .cumulative_confidence ):
                break 
            color_tuple =confidence_to_rgba (self .cumulative_confidence [i ])
            if color_tuple [3 ]==0 :
                continue 
            gx_c ,gy_c =self .image_to_canvas (gx ,gy )
            draw_handle .rectangle (
            [gx_c -half_step ,gy_c -half_step ,
            gx_c +half_step ,gy_c +half_step ],
            fill =color_tuple )
        self .confidence_photo =ImageTk .PhotoImage (overlay )
        self .main_canvas .create_image (
        0 ,0 ,anchor ="nw",image =self .confidence_photo )
    def _draw_coverage_circles_planning (self ,canvas_w ,canvas_h ):
        if not self .round_nodes_list :
            return 
        radius_px =self .spore_radius_meters *self .scale_px_per_meter 
        overlay =Image .new ("RGBA",(canvas_w ,canvas_h ),(0 ,0 ,0 ,0 ))
        draw_handle =ImageDraw .Draw (overlay )
        for nodes in self .round_nodes_list :
            for node in nodes :
                nx ,ny ,r =node ['real_xy'][0 ],node ['real_xy'][1 ],radius_px 
                nx_c ,ny_c =self .image_to_canvas (nx ,ny )
                draw_handle .ellipse (
                [nx_c -r ,ny_c -r ,nx_c +r ,ny_c +r ],
                fill =(27 ,42 ,36 ,22 ),outline =(76 ,209 ,55 ,55 ),width =1 )
                draw_handle .ellipse (
                [nx_c -r *0.6 ,ny_c -r *0.6 ,
                nx_c +r *0.6 ,ny_c +r *0.6 ],
                fill =(34 ,62 ,50 ,40 ),outline =(76 ,209 ,55 ,80 ),width =1 )
                draw_handle .ellipse (
                [nx_c -r *0.3 ,ny_c -r *0.3 ,
                nx_c +r *0.3 ,ny_c +r *0.3 ],
                fill =(46 ,91 ,70 ,70 ),outline =(186 ,220 ,88 ,120 ),width =1 )
        self .circles_photo =ImageTk .PhotoImage (overlay )
        self .main_canvas .create_image (
        0 ,0 ,anchor ="nw",image =self .circles_photo )
    def _draw_planning_legend (self ,canvas_w ,canvas_h ):
        legend_w ,legend_h =140 ,26 
        lx =canvas_w -legend_w -20 
        ly =canvas_h -legend_h -20 
        self .main_canvas .create_rectangle (
        lx ,ly ,lx +legend_w ,ly +legend_h ,
        fill =self .color_background ,outline =self .color_dim ,width =1 )
        bar_y =ly +5 
        bar_h =legend_h -10 
        bar_x =lx +8 
        bar_w =80 
        for i in range (bar_w ):
            conf =i /bar_w 
            rgba =confidence_to_rgba (conf )
            hex_color =f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}"
            self .main_canvas .create_line (
            bar_x +i ,bar_y ,bar_x +i ,bar_y +bar_h ,fill =hex_color )
        self .main_canvas .create_text (
        bar_x ,bar_y +bar_h +2 ,text ="0",
        fill =self .color_dim ,font =("Consolas",6 ),anchor ="n")
        self .main_canvas .create_text (
        bar_x +bar_w ,bar_y +bar_h +2 ,text ="1",
        fill =self .color_dim ,font =("Consolas",6 ),anchor ="n")
        self .main_canvas .create_text (
        bar_x +bar_w +24 ,bar_y +bar_h /2 ,text ="置信度",
        fill =self .color_dim ,font =("微软雅黑",7 ))
    def _draw_path_arrow (self ,x1 ,y1 ,x2 ,y2 ,color ):
        mid_x =x1 +0.75 *(x2 -x1 )
        mid_y =y1 +0.75 *(y2 -y1 )
        angle =math .atan2 (y2 -y1 ,x2 -x1 )
        arrow_length =10 
        arrow_width =5 
        p1 =(mid_x +arrow_length *math .cos (angle ),
        mid_y +arrow_length *math .sin (angle ))
        p2 =(mid_x +arrow_width *math .cos (angle +math .pi *0.85 ),
        mid_y +arrow_width *math .sin (angle +math .pi *0.85 ))
        p3 =(mid_x +arrow_width *math .cos (angle -math .pi *0.85 ),
        mid_y +arrow_width *math .sin (angle -math .pi *0.85 ))
        self .main_canvas .create_polygon (
        p1 [0 ],p1 [1 ],p2 [0 ],p2 [1 ],p3 [0 ],p3 [1 ],
        fill =color ,outline ="")

    def _load_satellite_image (self ):
        if not HAS_PILLOW :
            messagebox .showerror ("Error","需要安装 Pillow 库以支持图像处理。")
            return 
        file_path =filedialog .askopenfilename (
        filetypes =[("Image files","*.png *.jpg *.jpeg *.bmp *.gif")])
        if not file_path :
            return 
        try :
            self .pil_image =Image .open (file_path )
            cw =self .main_canvas .winfo_width ()
            ch =self .main_canvas .winfo_height ()
            if cw <10 :
                cw ,ch =1000 ,800 
            self .pil_image .thumbnail ((cw ,ch ))
            self .tk_photo_image =ImageTk .PhotoImage (self .pil_image )
            self .field_polygon =[]
            self .undo_stack =[]
            self .sampling_points =[]
            self ._clear_heatmap_caches ()
            self .round_nodes_list =[]
            self .round_tours =[]
            self ._update_canvas_dimensions ()
            self ._draw_planning_view ()
            self .status_variable .set ("MAP LOADED: 卫星影像加载完成。")
        except Exception as error :
            messagebox .showerror ("Error",f"图像解析异常: {error}")
    def _start_polygon_drawing (self ):
        self .is_drawing_polygon =True 
        self .field_polygon =[]
        self .undo_stack =[]
        self .sampling_points =[]
        self .round_nodes_list =[]
        self .round_tours =[]
        self ._draw_planning_view ()
        self .status_variable .set ("DIGITIZING: 左键标定顶点，右键撤销。首边方向 = 垄向。")
    def _close_polygon (self ):
        if len (self .field_polygon )<3 :
            messagebox .showwarning ("Warning","多边形至少需要 3 个顶点。")
            return 
        self .is_drawing_polygon =False 
        self ._draw_planning_view ()
        area_px =polygon_area (self .field_polygon )
        area_m2 =area_px /(self .scale_px_per_meter **2 )if self .scale_px_per_meter >0 else 0 
        self .status_variable .set (
        f"TOPOLOGY CLOSED: 面积≈{area_m2:.0f} m², {len(self.field_polygon)} 个顶点。")
    def _parse_parameters (self ):
        try :
            ref_len =float (self .entry_ref_length .get ())
            ridge_dist =float (self .entry_ridge_distance .get ())
            num_samples =int (self .entry_samples_per_round .get ())
            spore_radius =float (self .entry_spore_radius .get ())
            num_rounds =int (self .entry_num_rounds .get ())
            vehicle_speed =float (self .entry_vehicle_speed .get ())
            return (ref_len ,ridge_dist ,num_samples ,
            spore_radius ,num_rounds ,vehicle_speed )
        except ValueError :
            messagebox .showerror ("参数错误","请输入合法的数值参数。")
            return None 
    def _solve_planning_pipeline (self ):
        if len (self .field_polygon )<3 :
            messagebox .showerror ("Error","请先闭合农田边界多边形。")
            return 
        params =self ._parse_parameters ()
        if not params :
            return 
        (ref_len_m ,ridge_dist_m ,num_samples ,spore_radius_m ,
        num_rounds ,vehicle_speed_ms )=params 
        self .status_variable .set ("CALCULATING: 正在求解覆盖矩阵...")
        self .root .update ()
        ref_x1 ,ref_y1 =self .field_polygon [0 ]
        ref_x2 ,ref_y2 =self .field_polygon [1 ]
        px_ref_len =math .hypot (ref_x2 -ref_x1 ,ref_y2 -ref_y1 )
        if px_ref_len <1.0 :
            messagebox .showerror ("Error","基准边像素长度过短，请重新标定。")
            return 
        scale =px_ref_len /ref_len_m 
        self .scale_px_per_meter =scale 
        self .reference_x_px =ref_x1 
        self .reference_y_px =ref_y1 
        self .spore_radius_meters =spore_radius_m 
        self .vehicle_speed_ms =vehicle_speed_ms 
        ridge_px =ridge_dist_m *scale 
        radius_px =spore_radius_m *scale 
        rotation_theta =math .atan2 (ref_y2 -ref_y1 ,ref_x2 -ref_x1 )
        cx ,cy =ref_x1 ,ref_y1 
        rotated_polygon =[
        rotate_point (x ,y ,cx ,cy ,-rotation_theta )
        for x ,y in self .field_polygon ]
        min_x =min (p [0 ]for p in rotated_polygon )
        max_x =max (p [0 ]for p in rotated_polygon )
        min_y =min (p [1 ]for p in rotated_polygon )
        max_y =max (p [1 ]for p in rotated_polygon )
        box_w =max_x -min_x 
        box_h =max_y -min_y 
        self .grid_step_px =max (
        4.0 *scale ,math .sqrt ((box_w *box_h )/1200.0 ))
        approx_ridges =max (1 ,box_h /ridge_px )
        step_px =max (1.5 *scale ,(box_w *approx_ridges )/800.0 )
        candidate_pool =[]
        self .ridge_database ={}
        scan_y =min_y +ridge_px /2.0 
        ridge_index =0 
        while scan_y <=max_y :
            intersections =scanline_intersections (scan_y ,rotated_polygon )
            for i in range (0 ,len (intersections )-1 ,2 ):
                seg_start ,seg_end =intersections [i ],intersections [i +1 ]
                self .ridge_database [ridge_index ]={
                'y_rot':scan_y ,
                'left_rot':seg_start ,
                'right_rot':seg_end }
                cur_x =seg_start +step_px 
                while cur_x <=seg_end -step_px :
                    candidate_pool .append ({
                    'real_xy':rotate_point (
                    cur_x ,scan_y ,cx ,cy ,rotation_theta ),
                    'rot_xy':(cur_x ,scan_y ),
                    'ridge_idx':ridge_index })
                    cur_x +=step_px 
            if intersections :
                ridge_index +=1 
            scan_y +=ridge_px 
        self .evaluation_grid =[]
        gx =min_x 
        while gx <=max_x :
            gy =min_y 
            while gy <=max_y :
                rx_ ,ry_ =rotate_point (gx ,gy ,cx ,cy ,rotation_theta )
                if point_in_polygon (rx_ ,ry_ ,self .field_polygon ):
                    self .evaluation_grid .append ((rx_ ,ry_ ))
                gy +=self .grid_step_px 
            gx +=self .grid_step_px 
        if not self .evaluation_grid or not candidate_pool :
            messagebox .showerror (
            "Error","算子空间结构异常，请检查标定范围或放宽参数。")
            return 
        total_candidates =len (candidate_pool )
        self .status_variable .set (
        f"CALCULATING: {total_candidates} 候选点, "
        f"{len(self.evaluation_grid)} 格网单元...")
        self .root .update ()
        evaluator =CoverageEvaluator (
        self .evaluation_grid ,candidate_pool ,radius_px )
        cumulative_conf =[0.0 ]*len (self .evaluation_grid )
        all_selected =[]
        def progress_callback (step ,total ):
            self .status_variable .set (
            f"CALCULATING: 第 {len(all_selected) + 1} 轮 "
            f"选点 {step}/{total} (候选池 {total_candidates} 点)")
            self .root .update ()
        for rnd in range (num_rounds ):
            selected ,cumulative_conf =evaluator .greedy_select (
            cumulative_conf ,num_samples ,progress_callback )
            all_selected .append (selected )
        self .cumulative_confidence =cumulative_conf 
        tours =[]
        segments =[]
        for nodes in all_selected :
            n =len (nodes )
            if n <2 :
                tours .append (list (range (n )))
                segments .append ([])
                continue 
            initial_tour =nearest_neighbor_tour (
            nodes ,self .ridge_database ,cx ,cy ,rotation_theta )
            optimized_tour =two_opt_improve (
            initial_tour ,nodes ,self .ridge_database ,
            cx ,cy ,rotation_theta )
            tours .append (optimized_tour )
            round_segs =[]
            for idx in range (n ):
                node_a =nodes [optimized_tour [idx ]]
                node_b =nodes [optimized_tour [(idx +1 )%n ]]
                dist_px ,waypoints =compute_headland_path (
                node_a ,node_b ,self .ridge_database ,
                cx ,cy ,rotation_theta )
                dist_m =dist_px /scale
                waypoints_m =[
                (round ((wp [0 ]-ref_x1 )/scale ,2 ),
                round ((wp [1 ]-ref_y1 )/scale ,2 ))
                for wp in waypoints ]
                round_segs .append ({
                'from':optimized_tour [idx ],
                'to':optimized_tour [(idx +1 )%n ],
                'dist_m':round (dist_m ,2 ),
                'time_s':round (dist_m /vehicle_speed_ms ,1 ),
                'waypoints_px':waypoints ,
                'waypoints_m':waypoints_m })
            segments .append (round_segs )
        self .round_nodes_list =all_selected 
        self .round_tours =tours 
        self .round_segments =segments 
        self .sampling_points =[]
        for rnd ,nodes in enumerate (all_selected ):
            for local_idx ,node in enumerate (nodes ):
                px ,py =node ['real_xy']
                self .sampling_points .append ({
                'point_id':f"R{rnd + 1}-P{local_idx + 1}",
                'real_xy':(px ,py ),
                'x_m':round ((px -ref_x1 )/scale ,2 ),
                'y_m':round ((py -ref_y1 )/scale ,2 ),
                'ridge_idx':node ['ridge_idx'],
                'round':rnd +1 ,
                'turbidity':None ,
                'risk':'pending',
                'read_time':'',
                'pcr_ct':None ,
                'pcr_conc':None ,
                'pcr_qual':'pending',
                'pcr_gene':None ,
                'pcr_verdict':''})
        self .field_polygon_meters =[
        (round ((x -ref_x1 )/scale ,2 ),
        round ((y -ref_y1 )/scale ,2 ))
        for x ,y in self .field_polygon ]
        covered =sum (1 for c in cumulative_conf if c >0.5 )
        total_cells =len (cumulative_conf )
        coverage_pct =(covered /total_cells *
        100 )if total_cells >0 else 0 
        avg_conf =sum (cumulative_conf )/total_cells if total_cells >0 else 0 
        total_time =sum (sum (s ['time_s']for s in rs )for rs in segments )
        total_dist =sum (sum (s ['dist_m']for s in rs )for rs in segments )
        self .status_variable .set (
        f"PLANNING DONE: {num_rounds} 轮 × ~{num_samples} 点 | "
        f"覆盖率 {coverage_pct:.1f}% | 均置信度 {avg_conf:.3f} | "
        f"总路程 {total_dist:.0f} m | 总时间 {total_time:.0f} s")
        self ._draw_planning_view ()

    def export_json (self ):
        if not self .sampling_points :
            messagebox .showwarning ("Warning","请先完成路径规划。")
            return
        file_path =filedialog .asksaveasfilename (
        defaultextension =".json",filetypes =[("JSON 文件","*.json")],
        title ="导出路径规划 JSON")
        if not file_path :
            return
        total_time =sum (
        sum (s ['time_s']for s in rs )for rs in self .round_segments )
        total_dist =sum (
        sum (s ['dist_m']for s in rs )for rs in self .round_segments )
        num_rounds =len (self .round_nodes_list )
        num_ridges =len (self .ridge_database )
        ridge_dist_m =0
        if num_ridges >=2 :
            y0 =self .ridge_database [0 ]['y_rot']
            y1 =self .ridge_database [1 ]['y_rot']
            ridge_dist_m =round (abs (y1 -y0 )/self .scale_px_per_meter ,2 )
        data ={
        "meta":{
        "version":"4.0",
        "software":"多模态智能巡检系统",
        "scale_px_per_m":round (self .scale_px_per_meter ,2 ),
        "field_area_m2":round (
        polygon_area (self .field_polygon )/
        (self .scale_px_per_meter **2 )
        if self .scale_px_per_meter >0 else 0 ,2 ),
        "path_summary":{
        "total_rounds":num_rounds ,
        "total_ridges":num_ridges ,
        "ridge_spacing_m":ridge_dist_m ,
        "total_distance_m":round (total_dist ,2 ),
        "total_time_s":round (total_time ,1 ),
        "vehicle_speed_ms":self .vehicle_speed_ms ,
        "spore_radius_m":self .spore_radius_meters
        }
        },
        "field_polygon":{
        "vertices_m":[[v [0 ],v [1 ]]
        for v in self .field_polygon_meters ]
        },
        "ridge_geometry":[
        {
        "ridge_id":ridge_idx ,
        "y_rot_px":round (info ['y_rot'],2 ),
        "left_rot_px":round (info ['left_rot'],2 ),
        "right_rot_px":round (info ['right_rot'],2 )
        }
        for ridge_idx ,info in self .ridge_database .items ()
        ],
        "sampling_points":[
        {
        "id":pt ['point_id'],
        "relative_m":[pt ['x_m'],pt ['y_m']],
        "ridge_idx":pt ['ridge_idx'],
        "round":pt ['round'],
        "turbidity":pt .get ('turbidity'),
        "risk":pt .get ('risk'),
        "pcr_ct":pt .get ('pcr_ct'),
        "pcr_conc":pt .get ('pcr_conc')
        }
        for pt in self .sampling_points
        ],
        "path_rounds":[]
        }
        for rnd_idx in range (num_rounds ):
            nodes =self .round_nodes_list [rnd_idx ]
            tour =self .round_tours [rnd_idx ]
            segs =self .round_segments [rnd_idx ]
            round_path =[]
            for seg_idx ,seg in enumerate (segs ):
                node_from =nodes [seg ['from']]
                node_to =nodes [seg ['to']]
                round_path .append ({
                "segment_index":seg_idx ,
                "from_node":seg ['from'],
                "to_node":seg ['to'],
                "from_point_id":f"R{rnd_idx + 1}-P{seg['from']+ 1}",
                "to_point_id":f"R{rnd_idx + 1}-P{seg['to']+ 1}",
                "from_m":[round ((node_from ['real_xy'][0 ]-
                self .reference_x_px )/self .scale_px_per_meter ,2 ),
                round ((node_from ['real_xy'][1 ]-
                self .reference_y_px )/self .scale_px_per_meter ,2 )],
                "to_m":[round ((node_to ['real_xy'][0 ]-
                self .reference_x_px )/self .scale_px_per_meter ,2 ),
                round ((node_to ['real_xy'][1 ]-
                self .reference_y_px )/self .scale_px_per_meter ,2 )],
                "distance_m":seg ['dist_m'],
                "time_s":seg ['time_s'],
                "travel_waypoints_m":seg ['waypoints_m']
                })
            tour_order =[tour [i ]for i in range (len (tour ))]
            data ["path_rounds"].append ({
            "round":rnd_idx +1 ,
            "tour_order":tour_order ,
            "num_segments":len (segs ),
            "round_distance_m":round (
            sum (s ['dist_m']for s in segs ),2 ),
            "round_time_s":round (
            sum (s ['time_s']for s in segs ),1 ),
            "segments":round_path
            })
        try :
            with open (file_path ,'w',encoding ='utf-8')as f :
                json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            self .status_variable .set (
            f"EXPORTED: {os.path.basename(file_path)}")
        except Exception as error :
            messagebox .showerror ("导出失败",f"{error}")
    def _export_planning_report (self ):
        if not self .sampling_points :
            messagebox .showwarning ("Warning","请先完成路径规划。")
            return 
        file_path =filedialog .asksaveasfilename (
        defaultextension =".txt",filetypes =[("文本文件","*.txt")],
        title ="导出规划报告")
        if not file_path :
            return 
        total_time =sum (
        sum (s ['time_s']for s in rs )for rs in self .round_segments )
        total_dist =sum (
        sum (s ['dist_m']for s in rs )for rs in self .round_segments )
        area_m2 =(
        polygon_area (self .field_polygon )/
        (self .scale_px_per_meter **2 )
        if self .scale_px_per_meter >0 else 0 )
        lines =[
        "="*50 ,
        "  多模态智能巡检系统 V3.0 —— 路径规划报告",
        f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "="*50 ,"",
        f"  地块面积: {area_m2:.0f} m²",
        f"  采样点总数: {len(self.sampling_points)}",
        f"  预估总路程: {total_dist:.0f} m",
        f"  预估总时间: {total_time:.0f} s",
        "","采样点清单:",
        ]
        for pt in self .sampling_points :
            lines .append (
            f"  {pt['point_id']:<10} "
            f"X = {pt['x_m']:>7.2f} m  Y = {pt['y_m']:>7.2f} m")
        try :
            with open (file_path ,'w',encoding ='utf-8')as f :
                f .write ('\n'.join (lines ))
            self .status_variable .set (
            f"EXPORTED: {os.path.basename(file_path)}")
        except Exception as error :
            messagebox .showerror ("导出失败",f"{error}")
    def _show_statistics_window (self ):
        if not self .sampling_points :
            messagebox .showwarning ("Warning","尚无数据。")
            return 
        window =tk .Toplevel (self .root )
        window .title ("综合统计摘要")
        window .geometry ("450x420")
        window .configure (bg =self .color_panel )
        window .transient (self .root )
        window .grab_set ()
        tk .Label (
        window ,text ="综合统计摘要",
        fg =self .color_info ,bg =self .color_panel ,
        font =("微软雅黑",14 ,"bold")
        ).pack (pady =15 )
        text_widget =tk .Text (
        window ,bg =self .color_background ,fg =self .color_text ,
        bd =0 ,font =("Consolas",10 ),padx =14 ,pady =14 )
        text_widget .pack (fill ="both",expand =True )
        n =len (self .sampling_points )
        r =len (set (p ['round']for p in self .sampling_points ))
        done =sum (1 for p in self .sampling_points 
        if p .get ('turbidity')is not None )
        high =sum (1 for p in self .sampling_points 
        if p .get ('risk')=='high')
        pcr =sum (1 for p in self .sampling_points 
        if p .get ('pcr_ct')is not None )
        area_m2 =(
        polygon_area (self .field_polygon )/
        (self .scale_px_per_meter **2 )
        if self .scale_px_per_meter >0 and self .field_polygon else 0 )
        info =[
        f"农田面积: {area_m2:,.0f} m²",
        f"采样点总数: {n}  轮次: {r}",
        f"粗定完成: {done}  高风险: {high}",
        f"PCR 完成: {pcr}",
        ]
        if self .round_segments :
            td =sum (
            sum (s ['dist_m']for s in rs )for rs in self .round_segments )
            tt =sum (
            sum (s ['time_s']for s in rs )for rs in self .round_segments )
            info +=[
            f"总行驶距离: {td:,.0f} m",
            f"预估总时间: {tt:.0f} s ({tt / 60:.1f} min)",
            ]
        text_widget .insert ("1.0","\n".join (info ))
        text_widget .config (state ="disabled")
        tk .Button (
        window ,text ="关闭",bg =self .color_card ,fg =self .color_text ,
        bd =0 ,padx =20 ,pady =4 ,font =("微软雅黑",10 ),
        command =window .destroy 
        ).pack (pady =14 )
    def _save_session (self ):
        if not self .field_polygon :
            messagebox .showwarning ("Warning","尚无数据可保存。")
            return 
        file_path =filedialog .asksaveasfilename (
        defaultextension =".json",filetypes =[("JSON 文件","*.json")],
        title ="保存工作会话")
        if not file_path :
            return 
        session_data ={
        "version":"3.0",
        "timestamp":datetime .now ().isoformat (),
        "scale":round (self .scale_px_per_meter ,4 ),
        "ref_point":[round (self .reference_x_px ,1 ),
        round (self .reference_y_px ,1 )],
        "radius_m":self .spore_radius_meters ,
        "speed_ms":self .vehicle_speed_ms ,
        "polygon":[[round (x ,1 ),round (y ,1 )]
        for x ,y in self .field_polygon ],
        "polygon_m":[[v [0 ],v [1 ]]for v in self .field_polygon_meters ],
        "sampling_points":[
        {
        "point_id":pt ['point_id'],
        "x_m":pt ['x_m'],"y_m":pt ['y_m'],
        "real_xy":list (pt ['real_xy']),
        "turbidity":pt .get ('turbidity'),
        "risk":pt .get ('risk'),
        "pcr_ct":pt .get ('pcr_ct'),
        "pcr_conc":pt .get ('pcr_conc'),
        "pcr_qual":pt .get ('pcr_qual')
        }
        for pt in self .sampling_points 
        ]
        }
        try :
            with open (file_path ,'w',encoding ='utf-8')as f :
                json .dump (session_data ,f ,ensure_ascii =False ,indent =2 )
            self .status_variable .set (
            f"SESSION SAVED: {os.path.basename(file_path)}")
        except Exception as error :
            messagebox .showerror ("保存失败",f"{error}")
    def _load_session (self ):
        file_path =filedialog .askopenfilename (
        filetypes =[("JSON 文件","*.json")],title ="恢复工作会话")
        if not file_path :
            return 
        try :
            with open (file_path ,'r',encoding ='utf-8')as f :
                s =json .load (f )
        except Exception as error :
            messagebox .showerror ("加载失败",f"{error}")
            return 
        self .scale_px_per_meter =s .get ('scale',1.0 )
        rp =s .get ('ref_point',[0 ,0 ])
        self .reference_x_px ,self .reference_y_px =rp [0 ],rp [1 ]
        self .spore_radius_meters =s .get ('radius_m',20.0 )
        self .vehicle_speed_ms =s .get ('speed_ms',0.5 )
        self .field_polygon =[
        (x ,y )for x ,y in s .get ('polygon',[])]
        self .field_polygon_meters =[
        (x ,y )for x ,y in s .get ('polygon_m',[])]
        self .sampling_points =[]
        for pt in s .get ('sampling_points',[]):
            rxy =pt .get ('real_xy',[0 ,0 ])
            self .sampling_points .append ({
            'point_id':pt ['point_id'],
            'real_xy':tuple (rxy ),
            'x_m':pt ['x_m'],'y_m':pt ['y_m'],
            'ridge_idx':pt .get ('ridge_idx',0 ),
            'round':pt .get ('round',1 ),
            'turbidity':pt .get ('turbidity'),
            'risk':pt .get ('risk','pending'),
            'read_time':pt .get ('read_time',''),
            'pcr_ct':pt .get ('pcr_ct'),
            'pcr_conc':pt .get ('pcr_conc'),
            'pcr_qual':pt .get ('pcr_qual','pending'),
            'pcr_gene':pt .get ('pcr_gene'),
            'pcr_verdict':pt .get ('pcr_verdict','')
            })
        self .is_drawing_polygon =False 
        self ._update_canvas_dimensions ()
        self ._redraw_current_view ()
        self .status_variable .set (
        f"SESSION LOADED: {os.path.basename(file_path)} —— "
        f"{len(self.sampling_points)} 个采样点已恢复。")
    def _batch_export_all (self ):
        if not self .sampling_points :
            messagebox .showwarning ("Warning","尚无数据。")
            return
        directory =filedialog .askdirectory (title ="选择批量导出目录")
        if not directory :
            return
        base_name =os .path .join (
        directory ,
        f"inspection_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        errors =[]
        files_written =[]
        total_time =sum (
        sum (s ['time_s']for s in rs )for rs in self .round_segments )
        total_dist =sum (
        sum (s ['dist_m']for s in rs )for rs in self .round_segments )
        num_rounds =len (self .round_nodes_list )
        ridge_dist_m =0
        if len (self .ridge_database )>=2 :
            y0 =self .ridge_database [0 ]['y_rot']
            y1 =self .ridge_database [1 ]['y_rot']
            ridge_dist_m =round (abs (y1 -y0 )/self .scale_px_per_meter ,2 )
        try :
            with open (base_name +".json",'w',encoding ='utf-8')as f :
                data ={
                "meta":{
                "version":"4.0",
                "software":"多模态智能巡检系统",
                "scale_px_per_m":round (self .scale_px_per_meter ,2 ),
                "field_area_m2":round (
                polygon_area (self .field_polygon )/
                (self .scale_px_per_meter **2 )
                if self .scale_px_per_meter >0 else 0 ,2 ),
                "path_summary":{
                "total_rounds":num_rounds ,
                "total_ridges":len (self .ridge_database ),
                "ridge_spacing_m":ridge_dist_m ,
                "total_distance_m":round (total_dist ,2 ),
                "total_time_s":round (total_time ,1 ),
                "vehicle_speed_ms":self .vehicle_speed_ms ,
                "spore_radius_m":self .spore_radius_meters
                }
                },
                "field_polygon":{
                "vertices_m":[[v [0 ],v [1 ]]
                for v in self .field_polygon_meters ]
                },
                "ridge_geometry":[
                {
                "ridge_id":rid ,
                "y_rot_px":round (info ['y_rot'],2 ),
                "left_rot_px":round (info ['left_rot'],2 ),
                "right_rot_px":round (info ['right_rot'],2 )
                }
                for rid ,info in self .ridge_database .items ()
                ],
                "sampling_points":[
                {
                "id":pt ['point_id'],
                "relative_m":[pt ['x_m'],pt ['y_m']],
                "ridge_idx":pt ['ridge_idx'],
                "round":pt ['round'],
                "turbidity":pt .get ('turbidity'),
                "risk":pt .get ('risk'),
                "pcr_ct":pt .get ('pcr_ct'),
                "pcr_conc":pt .get ('pcr_conc')
                }
                for pt in self .sampling_points
                ],
                "path_rounds":[]
                }
                for rnd_idx in range (num_rounds ):
                    nodes =self .round_nodes_list [rnd_idx ]
                    tour =self .round_tours [rnd_idx ]
                    segs =self .round_segments [rnd_idx ]
                    round_path =[]
                    for seg_idx ,seg in enumerate (segs ):
                        round_path .append ({
                        "segment_index":seg_idx ,
                        "from_node":seg ['from'],
                        "to_node":seg ['to'],
                        "from_point_id":f"R{rnd_idx + 1}-P{seg['from']+ 1}",
                        "to_point_id":f"R{rnd_idx + 1}-P{seg['to']+ 1}",
                        "distance_m":seg ['dist_m'],
                        "time_s":seg ['time_s'],
                        "travel_waypoints_m":seg ['waypoints_m']
                        })
                    tour_order =[tour [i ]for i in range (len (tour ))]
                    data ["path_rounds"].append ({
                    "round":rnd_idx +1 ,
                    "tour_order":tour_order ,
                    "num_segments":len (segs ),
                    "round_distance_m":round (
                    sum (s ['dist_m']for s in segs ),2 ),
                    "round_time_s":round (
                    sum (s ['time_s']for s in segs ),1 ),
                    "segments":round_path
                    })
                json .dump (data ,f ,ensure_ascii =False ,indent =2 )
            files_written .append ("JSON")
        except Exception as e :
            errors .append (f"JSON: {e}")
        try :
            with open (base_name +"_sensing.csv",'w',
            newline ='',encoding ='utf-8-sig')as f :
                writer =csv .writer (f )
                writer .writerow (
                ['采样点','X','Y','浊度','风险','时间'])
                for pt in self .sampling_points :
                    writer .writerow ([
                    pt ['point_id'],pt ['x_m'],pt ['y_m'],
                    f"{pt['turbidity']:.1f}"if pt .get (
                    'turbidity')else '',
                    self ._risk_text (pt .get ('risk','pending')),
                    pt .get ('read_time','')])
            files_written .append ("CSV(sensing)")
        except Exception as e :
            errors .append (f"CSV(sensing): {e}")
        try :
            with open (base_name +"_path_route.csv",'w',
            newline ='',encoding ='utf-8-sig')as f :
                writer =csv .writer (f )
                writer .writerow (
                ['途经点全局序号','轮次','段序号','途经点类型',
                'X_m','Y_m','累计距离_m','段内距离_m','段时间_s'])
                cumulative_dist =0.0
                wp_global_idx =0
                for rnd_idx in range (len (self .round_nodes_list )):
                    segs =self .round_segments [rnd_idx ]
                    for seg_idx ,seg in enumerate (segs ):
                        wps =seg ['waypoints_m']
                        if len (wps )<2 :
                            continue
                        start_i =0 if seg_idx ==0 else 1
                        for wp_idx in range (start_i ,len (wps )):
                            wp =wps [wp_idx ]
                            if wp_idx ==start_i :
                                if seg_idx ==0 :
                                    wp_type ="采样停靠点"
                                else :
                                    wp_type ="采样停靠点"
                            elif wp_idx ==len (wps )-1 :
                                wp_type ="采样停靠点"
                            elif len (wps )==4 and wp_idx ==2 :
                                wp_type ="垄端地头转向点"
                            else :
                                wp_type ="垄端地头转向点"
                            if wp_idx ==start_i :
                                tsp =0
                            else :
                                frac =(wp_idx -start_i )/(len (wps )-start_i )
                                tsp =round (seg ['time_s']*frac ,1 )
                            seg_dist =round (
                            seg ['dist_m']*(wp_idx -start_i +1 )/
                            (len (wps )-start_i ),2 )
                            writer .writerow ([
                            wp_global_idx +1 ,
                            rnd_idx +1 ,seg_idx +1 ,
                            wp_type ,
                            wp [0 ],wp [1 ],
                            round (cumulative_dist ,2 ),
                            seg ['dist_m'],
                            tsp ])
                            wp_global_idx +=1
                        cumulative_dist +=seg ['dist_m']
            files_written .append ("CSV(path_route)")
        except Exception as e :
            errors .append (f"CSV(path_route): {e}")
        self .status_variable .set (
        f"BATCH EXPORT: {len(files_written)} 个文件。")
        messagebox .showinfo (
        "批量导出完成",
        f"已导出 {len(files_written)} 个文件至:\n{directory}")
    def _clear_all_data (self ):
        self .field_polygon =[]
        self .field_polygon_meters =[]
        self .undo_stack =[]
        self .sampling_points =[]
        self .round_nodes_list =[]
        self .round_tours =[]
        self .round_segments =[]
        self .cumulative_confidence =[]
        self .evaluation_grid =[]
        self .ridge_database ={}
        self .selected_point_index =-1
        self ._draw_planning_view ()
        self .status_variable .set ("SYS READY: 画布已清空，等待重新标定。")

    def _on_window_close (self ):
        self .root .destroy ()
if __name__ =="__main__":
    root_window =tk .Tk ()
    application =InspectionSystem (root_window )
    root_window .mainloop ()
