import matplotlib
matplotlib.use('Agg')

import schemdraw
import schemdraw.flow as flow
import schemdraw.segments as schemseg
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser
import sys
import os

import matplotlib.pyplot as plt

# Global matplotlib font configuration for massive text
plt.rcParams.update({'font.size': 75, 'axes.labelsize': 75, 'xtick.labelsize': 75, 'ytick.labelsize': 75})

# Set encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Monkey-patch schemdraw to handle special characters in labels during size measurement
import schemdraw.flow.flow
import schemdraw.backends.svg as schem_svg

_original_labelsize = schemdraw.flow.flow.labelsize
def _safe_labelsize(label, pad=0.125):
    if hasattr(label, 'label') and isinstance(label.label, str):
        original_text = label.label
        label.label = original_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        try:
            res = _original_labelsize(label, pad)
        finally:
            label.label = original_text
        return res
    return _original_labelsize(label, pad)
schemdraw.flow.flow.labelsize = _safe_labelsize

_original_text_size = schem_svg.text_size
def _safe_text_size(text, font=None, size=14, **kwargs):
    if isinstance(text, str):
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return _original_text_size(text, font=font, size=size, **kwargs)
schem_svg.text_size = _safe_text_size


class PreProcess(flow.Box):
    """GOST Predefined Process (Procedure call)"""
    def __init__(self, *args, **kwargs):
        kwargs['fill'] = kwargs.get('fill', 'white')
        super().__init__(*args, **kwargs)


# --- FIXED Preparation: do NOT inherit from flow.Box (no hidden rectangle) ---
import schemdraw.segments as schemseg
import re
from schemdraw.elements import Element

class Preparation(Element):
    """GOST Preparation (For loop hexagon) - strictly horizontal"""

    def __init__(self, w=4.0, h=1.6, **kwargs):
        super().__init__(**kwargs)

        # slant_w is the horizontal distance from the tip to the vertical edge start
        slant_w = 0.4 * h
        slant_w = min(slant_w, 0.4 * w)

        x0 = -w / 2
        x1 = -w / 2 + slant_w
        x2 =  w / 2 - slant_w
        x3 =  w / 2
        y0 = -h / 2
        y1 =  h / 2

        # Vertices for a symmetrical horizontal hexagon
        v = [
            (x0, 0),   # left tip
            (x1, y1),  # top-left
            (x2, y1),  # top-right
            (x3, 0),   # right tip
            (x2, y0),  # bottom-right
            (x1, y0),  # bottom-left
        ]
        self.segments.append(schemseg.SegmentPoly(v))

        # Anchors
        self.anchors["W"] = (x0, 0)
        self.anchors["E"] = (x3, 0)
        self.anchors["N"] = (0, y1)
        self.anchors["S"] = (0, y0)
        self.anchors["NW"] = (x0, y1)
        self.anchors["NE"] = (x3, y1)
        self.anchors["SW"] = (x0, y0)
        self.anchors["SE"] = (x3, y0)
        self.bbox = ((x0, y0), (x3, y1))


class FlowchartRenderer:
    def __init__(self):
        self.d = schemdraw.Drawing(show=False, canvas='matplotlib')
        import logging
        logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

        plt.rcParams['font.family'] = 'System'
        plt.rcParams['font.weight'] = 'bold'
        self.d.config(fontsize=75, margin=2.5, lw=10, font='System')

        self.scale = 1.9
        self.axis_x = 0.0
        self.last_pos = (self.axis_x, 0)
        self.max_y = 0
        self.return_points = []
        self.lane_idx = 0

        # >>> IMPORTANT: reduced merge gap for tighter layout
        self.merge_gap = 5.0  # Final balanced gap

        self.blocks_bboxes = []  # Track all blocks to avoid line crossings

    def wrap_text(self, text, max_width=24):
        import textwrap
        return '\n'.join(textwrap.wrap(text, width=max_width))

    def draw_open_arrow(self, point, direction='down'):
        L = 0.8
        W = 0.6
        if direction == 'down':
            self.d.add(flow.Line().at(point).to((point[0]-W, point[1]+L)))
            self.d.add(flow.Line().at(point).to((point[0]+W, point[1]+L)))
        elif direction == 'right':
            self.d.add(flow.Line().at(point).to((point[0]-L, point[1]+W)))
            self.d.add(flow.Line().at(point).to((point[0]-L, point[1]-W)))
        elif direction == 'left':
            self.d.add(flow.Line().at(point).to((point[0]+L, point[1]+W)))
            self.d.add(flow.Line().at(point).to((point[0]+L, point[1]-W)))
        elif direction == 'up':
            self.d.add(flow.Line().at(point).to((point[0]-W, point[1]-L)))
            self.d.add(flow.Line().at(point).to((point[0]+W, point[1]-L)))

    def find_safe_x(self, x_suggest, y_start, y_end, direction='right', margin=2.5):
        """Find the nearest X that doesn't intersect any block in [y1, y2]"""
        current_x = x_suggest
        # Narrow the range slightly to avoid colliding with the block we are exiting/entering
        y_min, y_max = min(y_start, y_end) + 0.1, max(y_start, y_end) - 0.1
        
        # Iteratively push X until no collisions
        while True:
            collision = False
            for bbox in self.blocks_bboxes:
                # Does the block overlap vertically with our line?
                if not (bbox['y2'] < y_min - 0.5 or bbox['y1'] > y_max + 0.5):
                    # Does the block intersect our X coordinate?
                    if (bbox['x1'] - margin) <= current_x <= (bbox['x2'] + margin):
                        collision = True
                        if direction == 'right':
                            current_x = bbox['x2'] + margin + 1.0
                        else:
                            current_x = bbox['x1'] - margin - 1.0
                        break # Re-check all blocks with new current_x
            if not collision:
                break
        return current_x

    def get_tiered_x(self, nest, direction='right'):
        """Calculate a 'tiered' X coordinate based on nesting level. 
        Lower nest (outer scope) results in larger offset (more 'external').
        """
        max_nest = 6
        base_offset = 35.0  
        # Inverse nesting: nest 0 gets largest offset
        step = 5.0         
        offset = base_offset + max(0, (max_nest - nest)) * step
        
        
        if direction == 'right':
            return self.axis_x + offset
        else:
            return self.axis_x - offset

    def add_line(self, length=None, direction='down', at=None, arrow=False, label=None):
        if length is None:
            length = self.scale
        if at is None:
            at = self.last_pos
            
        if direction == 'down' and label:
            shift_len = length * 0.35
            line_shift = flow.Line().at(at).down(shift_len)
            l_shift = self.d.add(line_shift)
            at = l_shift.end
            length = length - shift_len
        line = flow.Line().at(at)
        if label:
            loc = 'top' if direction in ['left', 'right'] else 'bottom'
            line.label(label, loc=loc, fontsize=75, ofst=1.8)
        if direction == 'down':
            line.down(length)
        elif direction == 'right':
            line.right(length)
        elif direction == 'left':
            line.left(length)
        elif direction == 'up':
            line.up(length)
        l = self.d.add(line)
        self.last_pos = l.end
        self.max_y = min(self.max_y, self.last_pos[1])
        if arrow:
            self.draw_open_arrow(l.end, direction=direction)
        return l

    def add_block(self, node_type, label, at=None, skip_line=False):
        if at is None:
            if not skip_line:
                self.add_line(arrow=True)
            # FORCE blocks to stay on the main axis to prevent "Pisa Tower"
            at = (self.axis_x, self.last_pos[1])
        else:
            # Ensure provided 'at' is also aligned if it was intended for the current axis
            # (Though at is usually dia.E etc, so we should be careful here)
            pass


        if node_type == 'for_loop':
            lbl = label
        else:
            lbl = self.wrap_text(label)

        lines_list = lbl.split('\n')
        lines = len(lines_list)
        max_line_len = max([len(l) for l in lines_list]) if lines_list else 1

        char_w = 1.35
        base_w = 21.0
        base_h = 6.0


        if node_type == 'decision':
            base_h = 10.0

        calc_w = max(base_w, max_line_len * char_w + (12.0 if node_type == 'for_loop' else 8.0))
        h = base_h + (lines - 1) * 2.1

        kwargs = {'at': at, 'anchor': 'N', 'fill': 'white'}
        label_kwargs = {'fontsize': 75}

        if node_type == 'start' or node_type == 'end':
            elm = flow.Terminal(w=max(18.0, calc_w), h=6.0, **kwargs).label(lbl, **label_kwargs)
        elif node_type == 'io':
            elm = flow.Data(w=calc_w + 4.0, h=h, **kwargs).label(lbl, **label_kwargs)
        elif node_type == 'statement' or node_type == 'return':
            elm = flow.Box(w=calc_w, h=h, **kwargs).label(lbl, **label_kwargs)
        elif node_type == 'call':
            elm = PreProcess(w=calc_w, h=h, **kwargs).label(lbl, **label_kwargs)
        elif node_type == 'decision':
            d_w = calc_w * 1.5 + 4.0
            d_h = h + 6.0 + (lines-1)*1.5
            elm = flow.Decision(w=d_w, h=d_h, **kwargs).label(lbl, **label_kwargs)
        elif node_type == 'for_loop':
            kwargs_for = {'at': at, 'anchor': 'N', 'theta': 0}
            # Reduced w and h significantly
            elm = Preparation(w=calc_w * 0.8 + 4.0, h=h * 0.8 + 1.0, **kwargs_for).label(lbl, loc='center', **label_kwargs)


        else:
            elm = flow.Box(w=calc_w, h=h, **kwargs).label(lbl, **label_kwargs)

        obj = self.d.add(elm)

        if node_type == 'call':
            offset = 2.1
            p1 = (obj.NW[0] + offset, obj.NW[1])
            p2 = (obj.SW[0] + offset, obj.SW[1])
            self.d.add(flow.Line().at(p1).to(p2))

            p3 = (obj.NE[0] - offset, obj.NE[1])
            p4 = (obj.SE[0] - offset, obj.SE[1])
            self.d.add(flow.Line().at(p3).to(p4))

        # Track bounding box
        self.blocks_bboxes.append({
            'x1': obj.NW[0], 'y1': obj.NW[1],
            'x2': obj.SE[0], 'y2': obj.SE[1]
        })

        # >>> IMPORTANT: do NOT lock X to at[0]; use real S anchor to avoid diagonals
        self.last_pos = (obj.S[0], obj.S[1])
        self.max_y = min(self.max_y, self.last_pos[1])
        return obj

    def merge_side_branch(self, source_pos, dead_main=False, target_y=None):
        if not dead_main:
            y = target_y if target_y is not None else (self.last_pos[1] - self.merge_gap)
            if abs(self.last_pos[1] - y) > 0.1:
                self.d.add(flow.Line().at(self.last_pos).toy(y))
            self.last_pos = (self.axis_x, y)
        else:
            y = target_y if target_y is not None else (min(self.max_y, source_pos[1]) - self.merge_gap)
            self.last_pos = (self.axis_x, y)

        y = self.last_pos[1]
        
        # Calculate safe path for the vertical drop from source_pos
        is_right = source_pos[0] > self.axis_x
        safe_x = self.find_safe_x(source_pos[0], source_pos[1], y, 
                                  direction='right' if is_right else 'left',
                                  margin=8.0)
        
        if abs(safe_x - source_pos[0]) > 0.1:
            # Shift the entry point to bypass blocks
            self.d.add(flow.Line().at(source_pos).tox(safe_x))
            source_pos = (safe_x, source_pos[1])

        # Vertical segment to target level
        if abs(source_pos[1] - y) > 0.1:
            self.d.add(flow.Line().at(source_pos).toy(y))
        
        # Horizontal segment to axis (only if not already there)
        if abs(safe_x - self.axis_x) > 0.1:
            self.d.add(flow.Line().at((safe_x, y)).tox(self.axis_x))
            
        self.max_y = min(self.max_y, y)
        if dead_main:
            self.last_pos = (self.axis_x, y)

    def render_nodes(self, nodes, nest=0, is_first=True):
        if nodes is None:
            return False
        is_terminated = False
        for i, node in enumerate(nodes):
            ntype = node[0]
            if is_terminated and ntype != 'end':
                break

            if ntype in ['start', 'end', 'statement', 'call', 'return', 'io']:
                if ntype == 'return':
                    self.add_block(ntype, node[1], skip_line=is_first)
                    is_first = False

                    # If on main axis, just go down if the next node is 'end'
                    if abs(self.axis_x) < 0.1:
                        if i < len(nodes) - 1 and nodes[i+1][0] == 'end':
                            # Just let it flow into the end block naturally
                            continue
                        else:
                            # Still terminated on main axis, but we want a line to stay
                            is_terminated = True
                            continue

                    # In a side branch: register the block's bottom as a return
                    # point so 'end' can merge it — but without a horizontal exit.
                    self.return_points.append(self.last_pos)
                    is_terminated = True

                elif ntype == 'end':
                    # Explicitly merge all active flows at a safe junction below everything
                    # Aggressively shorten the final section as requested (1/4 of merge_gap)
                    final_gap = self.merge_gap / 4.0
                    
                    if self.return_points or not is_terminated:
                        y = self.max_y - final_gap
                        
                        # Merge main flow if it's still alive (not terminated by return)
                        if not is_terminated:
                            self.merge_side_branch(self.last_pos, dead_main=True, target_y=y)
                        
                        # Join all return highways to the axis at junction level y
                        if self.return_points:
                            right_rps = sorted([rp for rp in self.return_points if rp[0] >= self.axis_x], key=lambda p: p[1], reverse=True)
                            left_rps = sorted([rp for rp in self.return_points if rp[0] < self.axis_x], key=lambda p: p[1], reverse=True)
                            
                            core_max_x = max([bbox['x2'] for bbox in self.blocks_bboxes]) + 15.0 if self.blocks_bboxes else self.axis_x + 30.0
                            core_min_x = min([bbox['x1'] for bbox in self.blocks_bboxes]) - 15.0 if self.blocks_bboxes else self.axis_x - 30.0
                            
                            outer_right_count = 0
                            for i, rp in enumerate(right_rps):
                                # Check if safe to drop straight down
                                is_safe = True
                                y_min, y_max = min(rp[1], y) + 0.1, max(rp[1], y) - 0.1
                                for bbox in self.blocks_bboxes:
                                    # If block overlaps vertically with our path
                                    if not (bbox['y2'] < y_min - 0.5 or bbox['y1'] > y_max + 0.5):
                                        # If block overlaps horizontally with rp[0]
                                        # We add a generous margin to detect near-misses properly
                                        if (bbox['x1'] - 6.0) <= rp[0] <= (bbox['x2'] + 6.0):
                                            is_safe = False
                                            break
                                            
                                if is_safe:
                                    highway_x = rp[0]
                                else:
                                    highway_x = core_max_x + (len(right_rps) - 1 - outer_right_count) * 6.0
                                    outer_right_count += 1
                                    
                                drop_y = rp[1] - 1.5
                                self.d.add(flow.Line().at(rp).toy(drop_y))
                                if abs(highway_x - rp[0]) > 0.1:
                                    self.d.add(flow.Line().at((rp[0], drop_y)).tox(highway_x))
                                if abs(drop_y - y) > 0.1:
                                    self.d.add(flow.Line().at((highway_x, drop_y)).toy(y))
                                if abs(highway_x - self.axis_x) > 0.1:
                                    self.d.add(flow.Line().at((highway_x, y)).tox(self.axis_x))
                                    
                            outer_left_count = 0
                            for i, rp in enumerate(left_rps):
                                is_safe = True
                                y_min, y_max = min(rp[1], y) + 0.1, max(rp[1], y) - 0.1
                                for bbox in self.blocks_bboxes:
                                    if not (bbox['y2'] < y_min - 0.5 or bbox['y1'] > y_max + 0.5):
                                        if (bbox['x1'] - 6.0) <= rp[0] <= (bbox['x2'] + 6.0):
                                            is_safe = False
                                            break
                                            
                                if is_safe:
                                    highway_x = rp[0]
                                else:
                                    highway_x = core_min_x - (len(left_rps) - 1 - outer_left_count) * 6.0
                                    outer_left_count += 1
                                    
                                drop_y = rp[1] - 1.5
                                self.d.add(flow.Line().at(rp).toy(drop_y))
                                if abs(highway_x - rp[0]) > 0.1:
                                    self.d.add(flow.Line().at((rp[0], drop_y)).tox(highway_x))
                                if abs(drop_y - y) > 0.1:
                                    self.d.add(flow.Line().at((highway_x, drop_y)).toy(y))
                                if abs(highway_x - self.axis_x) > 0.1:
                                    self.d.add(flow.Line().at((highway_x, y)).tox(self.axis_x))
                                
                        self.return_points = []
                        is_terminated = False # Junction established

                    # Final block placement with shorter connecting line
                    if not is_first and not is_terminated:
                        self.add_line(length=final_gap, arrow=True)
                        self.add_block(ntype, node[1], skip_line=True)
                    else:
                        self.add_block(ntype, node[1], skip_line=is_first)
                        
                    is_first = False
                    is_terminated = True

                else:
                    self.add_block(ntype, node[1], skip_line=is_first)
                    is_first = False

            elif ntype == 'while' or ntype == 'for_loop':
                cond_label = node[1]
                body_nodes = node[2]
                dia = self.add_block('decision' if ntype == 'while' else 'for_loop', cond_label, skip_line=is_first)
                is_first = False

                self.add_line(2.5, 'down', arrow=False, label='Да')
                body_term = self.render_nodes(body_nodes, nest + 1, is_first=False)

                block_w = dia.W[0] - dia.E[0]
                offset_l = max(14.4 + nest * 4.8, abs(block_w)/2 + 5.0)

                if not body_term:
                    # Спускаемся вниз от тела цикла
                    l1 = self.add_line(2.5, 'down')

                    if ntype == 'for_loop':
                        # GOST: return cycle with a tiered P-shaped line on the left
                        # Calculate tiered X for loopback (left side)
                        loop_x = self.get_tiered_x(nest, direction='left')
 
                        # 1. Left (outside blocks)
                        loop_x = self.find_safe_x(loop_x, l1.end[1], dia.W.y, direction='left', margin=8.0)
                        p1 = self.d.add(flow.Line().at(l1.end).tox(loop_x))

                        # 2. Вверх до уровня левого угла hex
                        entry_y = dia.W.y
                        p2 = self.d.add(flow.Line().at((loop_x, l1.end[1])).toy(entry_y))

                        # 3. Вправо к левому краю hex
                        self.d.add(flow.Line().at((loop_x, entry_y)).tox(dia.W))

                        # Стрелка в цикл
                        self.draw_open_arrow(dia.W, direction='right')
                    else:
                        # Regular while loopback
                        loop_x = self.get_tiered_x(nest, direction='left')
                        loop_x = self.find_safe_x(loop_x, l1.end[1], dia.N[1] + 1.2, direction='left', margin=6.0)
                        l2 = self.d.add(flow.Line().at(l1.end).tox(loop_x))
                        l3 = self.d.add(flow.Line().at(l2.end).toy(dia.N[1] + 1.2))
                        self.d.add(flow.Line().at(l3.end).tox(dia.N[0]))
                        self.draw_open_arrow((dia.N[0], dia.N[1] + 1.2), direction='right' if l3.end[0] < dia.N[0] else 'left')

                # Decision exit (False/No) branch with stub to prevent crowding
                tiered_no_x = self.get_tiered_x(nest, direction='right')
                # 1. Short stub (increased to 10.0 to clear wide blocks)
                stub = self.d.add(flow.Line().at(dia.E).right(10.0).label('Нет', loc='top', fontsize=75, ofst=1.8))
                # 2. Horizontal segment to highway
                no_line = self.d.add(flow.Line().at(stub.end).tox(tiered_no_x))

                # >>> IMPORTANT: merge lower, using merge_gap
                # For loops, the main flow ends with a loopback (or terminal), 
                # so it should NOT connect to the next block.
                self.merge_side_branch(no_line.end, dead_main=True, target_y=self.max_y - self.merge_gap)

            elif ntype == 'if':
                cond_label = node[1]
                cons_nodes = node[2]
                alt_nodes = node[3]
                dia = self.add_block('decision', cond_label, skip_line=is_first)
                is_first = False

                prev_axis = self.axis_x

                if alt_nodes:
                    # Full if-else structure
                    # Tiered offsets: outer scopes are further out
                    base_tiered_x_yes = self.get_tiered_x(nest, direction='left')
                    base_tiered_x_no = self.get_tiered_x(nest, direction='right')
                    
                    self.axis_x = base_tiered_x_yes
                    # Stub for Yes branch (increased to 10.0)
                    stub_yes = self.d.add(flow.Line().at(dia.W).left(10.0).label('Да', loc='top', fontsize=75, ofst=1.8))
                    self.d.add(flow.Line().at(stub_yes.end).tox(self.axis_x))
                    self.last_pos = (self.axis_x, dia.W[1])
                    self.add_line(1.2, 'down', arrow=False)
                    cons_term = self.render_nodes(cons_nodes, nest + 1, is_first=False)
                    cons_exit_pos = self.last_pos
 
                    self.axis_x = base_tiered_x_no
                    self.axis_x = self.find_safe_x(self.axis_x, dia.E[1], dia.E[1]-10.0, direction='right', margin=8.0)
                    # Stub for No branch (increased to 10.0)
                    stub_no = self.d.add(flow.Line().at(dia.E).right(10.0).label('Нет', loc='top', fontsize=75, ofst=1.8))
                    self.d.add(flow.Line().at(stub_no.end).tox(self.axis_x))
                    self.last_pos = (self.axis_x, dia.E[1])
                    self.add_line(1.2, 'down', arrow=False)
                    alt_term = self.render_nodes(alt_nodes, nest + 1, is_first=False)
                    alt_exit_pos = self.last_pos

                    self.axis_x = prev_axis
                    merge_y = self.max_y - self.merge_gap

                    if not cons_term:
                        self.merge_side_branch(cons_exit_pos, dead_main=True, target_y=merge_y)
                    if not alt_term:
                        self.merge_side_branch(alt_exit_pos, dead_main=True, target_y=merge_y)

                    if not cons_term or not alt_term:
                        self.max_y = min(self.max_y, merge_y)
                        self.last_pos = (self.axis_x, merge_y)
                    if cons_term and alt_term:
                        is_terminated = True

                else:
                    alt_term = False
                    # 'Нет' (False) path goes straight down - main continuation
                    self.add_line(1.2, 'down', arrow=False, label='Нет')
                    no_exit_pos = self.last_pos
 
                    # 'Да' (True) path goes to the right - side branch (often early exit)
                    # Use tiered X for hierarchical routing
                    tiered_x = self.get_tiered_x(nest, direction='right')
                    
                    prev_axis = self.axis_x
                    self.axis_x = tiered_x
                    # Ensure axis is safely to the right of the diamond and other blocks
                    self.axis_x = max(self.axis_x, dia.E[0] + 15.0)
                    self.axis_x = self.find_safe_x(self.axis_x, dia.E[1], dia.E[1]-10.0, direction='right', margin=8.0)
                    
                    # Stub for 'Да' branch (True path goes to the right)
                    stub_yes = self.d.add(flow.Line().at(dia.E).right(10.0).label('Да', loc='top', fontsize=75, ofst=1.8))
                    self.d.add(flow.Line().at(stub_yes.end).tox(self.axis_x))
                    self.last_pos = (self.axis_x, dia.E[1])
                    self.add_line(1.2, 'down', arrow=False)
                    cons_term = self.render_nodes(cons_nodes, nest + 1, is_first=False)
                    cons_exit_pos = self.last_pos

                    self.axis_x = prev_axis
                    merge_y = self.max_y - self.merge_gap

                    # Merge 'Да' branch back if not terminated
                    if not cons_term:
                        self.merge_side_branch(cons_exit_pos, dead_main=True, target_y=merge_y)

                    # Merge 'Нет' branch (main flow) down to the merge point
                    self.merge_side_branch(no_exit_pos, dead_main=True, target_y=merge_y)

                    self.max_y = min(self.max_y, merge_y)
                    self.last_pos = (self.axis_x, merge_y)

                    if cons_term and alt_term:
                        is_terminated = True

        return is_terminated

    def save(self, filename):
        self.d.save(filename, transparent=False)
        # prevent "More than 20 figures opened"
        plt.close('all')


def get_cpp_parser():
    CPP_LANGUAGE = Language(tscpp.language())
    parser = Parser(CPP_LANGUAGE)
    return parser


def get_func_name(n, code_bytes):
    def find_func_decl(n):
        if n.type == 'function_declarator':
            return n
        for c in n.children:
            res = find_func_decl(c)
            if res:
                return res
        return None

    fdecl = find_func_decl(n)
    if fdecl:
        def find_id(n):
            if n.type == 'identifier':
                return n
            for c in n.children:
                res = find_id(c)
                if res:
                    return res
            return None
        name_node = find_id(fdecl)
        if name_node:
            return code_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
    return "unknown"


def extract_all_functions(root_node, code_bytes):
    functions = {}
    for node in root_node.children:
        if node.type == 'function_definition':
            name = get_func_name(node, code_bytes)
            # Avoid processing 'main' here as it is handled by main_vertical.py/main_flow.py
            if name == 'main':
                continue
                
            body = None
            for child in node.children:
                if child.type == 'compound_statement':
                    body = child
                    break
            if name and body:
                nodes = [('start', "Начало")]
                nodes.extend(process_compound(body, code_bytes))
                nodes.append(('end', 'Конец'))
                functions[name] = nodes
    return functions

def process_single_node(node, code_bytes):
    if node.type == 'expression_statement':
        txt = code_bytes[node.start_byte:node.end_byte].decode('utf8').strip(';').strip()
        txt = re.sub(r'\s+', ' ', txt)
        def has_call(n):
            if n.type == 'call_expression':
                return True
            for c in n.children:
                if has_call(c):
                    return True
            return False
        
        if 'cin >>' in txt or 'cout <<' in txt:
            return [('io', txt)]
        elif has_call(node):
            return [('call', txt)]
        elif 'return' in txt: # This check is a bit weak, better to use tree-sitter for return_statement
            return [('return', txt)]
        else:
            return [('statement', txt)]
    elif node.type == 'declaration':
        # Declarations can have multiple declarators, some with initializers
        # We only care about initializers for flowchart purposes
        extracted_declarations = []
        for c in node.children:
            if c.type == 'init_declarator':
                txt = code_bytes[c.start_byte:c.end_byte].decode('utf8').strip()
                txt = re.sub(r'\s+', ' ', txt)
                if txt.startswith('*'):
                    txt = txt[1:].strip()
                extracted_declarations.append(('statement', txt))
        return extracted_declarations
    return []


def process_compound(node, code_bytes):
    extracted = []
    for child in node.children:
        if child.type in ['expression_statement', 'declaration']:
            extracted.extend(process_single_node(child, code_bytes))

        elif child.type == 'while_statement':
            cond_node = child.child_by_field_name('condition')
            if cond_node:
                cond = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip()
                if cond.startswith('(') and cond.endswith(')'):
                    cond = cond[1:-1].strip()
            else:
                cond = '???'
            body = child.child_by_field_name('body')
            extracted.append(('while', cond, process_node_or_compound(body, code_bytes)))

        elif child.type == 'if_statement':
            cond_node = child.child_by_field_name('condition')
            if cond_node:
                cond = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip()
                if cond.startswith('(') and cond.endswith(')'):
                    cond = cond[1:-1].strip()
            else:
                cond = '???'
            consequent = None
            alternative = None
            seen_condition = False
            for c in child.children:
                if c.type == 'condition_clause':
                    seen_condition = True
                elif c.type == 'else_clause':
                    for ec in c.children:
                        if ec.type != 'else':
                            alternative = ec
                            break
                elif seen_condition and c.type not in ['if', 'else']:
                    consequent = c
            extracted.append(('if', cond, process_node_or_compound(consequent, code_bytes),
                              process_node_or_compound(alternative, code_bytes) if alternative else None))

        elif child.type == 'for_statement':
            brackets_content = []
            capture = False
            for gc in child.children:
                if gc.type == '(':
                    capture = True
                    continue
                if gc.type == ')':
                    capture = False
                    break
                if capture:
                    brackets_content.append(code_bytes[gc.start_byte:gc.end_byte].decode('utf8').strip())

            raw_cond = ' '.join(brackets_content)
            raw_cond = raw_cond.replace(' ;', ';').replace('; ', '; ')

            import re
            type_pattern = r'^(?:int|long|char|bool|double|float|unsigned|size_t|auto|void|unsigned\s+int)\s*\*?\s*'
            parts = [p.strip() for p in raw_cond.split(';')]
            if parts:
                parts[0] = re.sub(type_pattern, '', parts[0])
            cond = '; '.join([p for p in parts if p])

            body = child.child_by_field_name('body')
            extracted.append(('for_loop', cond, process_node_or_compound(body, code_bytes)))

        elif child.type == 'switch_statement':
            # Handle switch as a chain of nested ifs for vertical layout
            cond_node = child.child_by_field_name('condition')
            switch_expr = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip()
            if switch_expr.startswith('(') and switch_expr.endswith(')'):
                switch_expr = switch_expr[1:-1].strip()

            body = child.child_by_field_name('body')
            if body:
                # Group cases
                cases = []
                current_case = None
                for bchild in body.children:
                    if bchild.type == 'case_statement':
                        val_node = bchild.child_by_field_name('value')
                        val_txt = code_bytes[val_node.start_byte:val_node.end_byte].decode('utf8').strip() if val_node else "???"
                        
                        # Process case body (everything after the colon)
                        # Tree-sitter includes follow-up statements as children of case_statement
                        case_body = []
                        for sub in bchild.children:
                            if sub.type not in [':', 'case', 'value']:
                                case_body.extend(process_node_or_compound(sub, code_bytes))
                        
                        cases.append(('if', f"{switch_expr} == {val_txt}", case_body, None))
                    elif bchild.type == 'default_statement':
                        case_body = []
                        for sub in bchild.children:
                            if sub.type not in [':', 'default']:
                                case_body.extend(process_node_or_compound(sub, code_bytes))
                        cases.append(('if', "default", case_body, None))

                # Build the nested chain backwards to form a longitudinal sequence
                if cases:
                    root_if = cases[0]
                    current = root_if
                    for next_case in cases[1:]:
                        # Convert next_case to the 'else' branch of the current one
                        # The 'if' node format is (ntype, label, cons, alt)
                        # We need to update current[3] = [next_case]
                        # But tuples are immutable, so we'll build it properly
                        pass
                    
                    # Re-build properly as nested if-else chain
                    def build_chain(idx):
                        if idx >= len(cases):
                            return []
                        c = cases[idx]
                        return [('if', c[1], c[2], build_chain(idx + 1))]
                    
                    chain = build_chain(0)
                    if chain:
                        extracted.append(chain[0])

        elif child.type == 'return_statement':
            txt = code_bytes[child.start_byte:child.end_byte].decode('utf8').strip(';').strip()
            extracted.append(('return', txt))

    return extracted


def process_node_or_compound(node, code_bytes):
    if node is None:
        return []
    if node.type == 'compound_statement':
        return process_compound(node, code_bytes)
    else:
        fake_compound = type('FakeNode', (), {'children': [node]})()
        return process_compound(fake_compound, code_bytes)


def main():
    if len(sys.argv) < 3:
        print("Usage: python cpp2flow.py <input_cpp_file> <output_dir>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]
    with open(input_file, 'r', encoding='utf-8') as f:
        code = f.read()

    parser = get_cpp_parser()
    tree = parser.parse(bytes(code, 'utf8'))

    functions = extract_all_functions(tree.root_node, bytes(code, 'utf8'))

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for name, nodes in functions.items():
        print(f"Generating flowchart for {name}...")
        renderer = FlowchartRenderer()
        renderer.render_nodes(nodes)

        output_file = os.path.join(output_dir, f"{name}.png")
        renderer.save(output_file)
        print(f"Saved {output_file}")


if __name__ == "__main__":
    main()
