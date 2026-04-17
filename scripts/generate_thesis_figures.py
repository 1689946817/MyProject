from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "thesis_assets" / "figures" / "system"
WIDTH = 1800
HEIGHT = 1000

BG = (247, 248, 250)
FRAME_FILL = (252, 252, 253)
FRAME_OUTLINE = (94, 107, 122)
TEXT = (31, 41, 55)
SUBTEXT = (71, 85, 105)
ARROW = (37, 99, 235)
SHADOW = (225, 229, 236)
WHITE = (255, 255, 255)

RED_FILL = (253, 230, 230)
RED_OUTLINE = (225, 29, 72)
BLUE_FILL = (224, 231, 255)
BLUE_OUTLINE = (37, 99, 235)
GREEN_FILL = (220, 252, 231)
GREEN_OUTLINE = (22, 163, 74)
AMBER_FILL = (254, 243, 199)
AMBER_OUTLINE = (217, 119, 6)
PURPLE_FILL = (237, 233, 254)
PURPLE_OUTLINE = (124, 58, 237)
SLATE_FILL = (226, 232, 240)
SLATE_OUTLINE = (71, 85, 105)


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: list[str] = []
    if bold:
        candidates.extend(
            [
                r"C:\Windows\Fonts\msyhbd.ttc",
                r"C:\Windows\Fonts\simhei.ttf",
            ]
        )
    candidates.extend(
        [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simsun.ttc",
        ]
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


PANEL_FONT = get_font(30, bold=True)
CARD_TITLE_FONT = get_font(28, bold=True)
CARD_BODY_FONT = get_font(22)


def make_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, WIDTH - 48, HEIGHT - 48), radius=34, fill=FRAME_FILL, outline=FRAME_OUTLINE, width=3)
    return image, draw


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, *, spacing: int = 8) -> tuple[int, int]:
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align="center")
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_shadowed_roundrect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    radius: int,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    width: int = 3,
    shadow_offset: int = 10,
) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle((x1 + shadow_offset, y1 + shadow_offset, x2 + shadow_offset, y2 + shadow_offset), radius=radius, fill=SHADOW)
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_chip(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    *,
    fill: tuple[int, int, int],
    text_fill: tuple[int, int, int] = WHITE,
) -> None:
    tw, th = text_size(draw, text, PANEL_FONT, spacing=4)
    pad_x = 22
    pad_y = 12
    draw.rounded_rectangle((x, y, x + tw + pad_x * 2, y + th + pad_y * 2), radius=20, fill=fill)
    draw.text((x + pad_x, y + pad_y - 2), text, fill=text_fill, font=PANEL_FONT)


def draw_panel(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    title: str,
    *,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
) -> None:
    draw_shadowed_roundrect(draw, xy, radius=30, fill=fill, outline=outline)
    x1, y1, _, _ = xy
    draw_chip(draw, x1 + 18, y1 + 16, title, fill=outline)


def draw_card(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    title: str,
    body: str = "",
    *,
    fill: tuple[int, int, int] = WHITE,
    outline: tuple[int, int, int] = FRAME_OUTLINE,
) -> None:
    x1, y1, x2, y2 = xy
    draw_shadowed_roundrect(draw, xy, radius=24, fill=fill, outline=outline, width=3, shadow_offset=8)
    title_w, title_h = text_size(draw, title, CARD_TITLE_FONT)
    title_x = x1 + ((x2 - x1) - title_w) / 2
    title_y = y1 + 26
    draw.multiline_text((title_x, title_y), title, fill=TEXT, font=CARD_TITLE_FONT, spacing=8, align="center")
    if body:
        body_w, body_h = text_size(draw, body, CARD_BODY_FONT)
        body_x = x1 + ((x2 - x1) - body_w) / 2
        body_y = title_y + title_h + 22
        if body_y + body_h > y2 - 24:
            body_y = y2 - body_h - 24
        draw.multiline_text((body_x, body_y), body, fill=SUBTEXT, font=CARD_BODY_FONT, spacing=8, align="center")


def draw_cylinder(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    title: str,
    body: str = "",
    *,
    fill: tuple[int, int, int] = WHITE,
    outline: tuple[int, int, int] = FRAME_OUTLINE,
) -> None:
    x1, y1, x2, y2 = xy
    arc_h = 34
    draw.rounded_rectangle((x1 + 8, y1 + 8, x2 + 8, y2 + 8), radius=20, fill=SHADOW)
    draw.rectangle((x1, y1 + arc_h // 2, x2, y2 - arc_h // 2), fill=fill, outline=outline, width=3)
    draw.ellipse((x1, y1, x2, y1 + arc_h), fill=fill, outline=outline, width=3)
    draw.arc((x1, y2 - arc_h, x2, y2), start=0, end=180, fill=outline, width=3)
    draw.line((x1, y1 + arc_h // 2, x1, y2 - arc_h // 2), fill=outline, width=3)
    draw.line((x2, y1 + arc_h // 2, x2, y2 - arc_h // 2), fill=outline, width=3)
    title_w, title_h = text_size(draw, title, CARD_TITLE_FONT)
    body_w, body_h = text_size(draw, body, CARD_BODY_FONT) if body else (0, 0)
    total_h = title_h + (18 + body_h if body else 0)
    start_y = y1 + ((y2 - y1) - total_h) / 2 + 6
    title_x = x1 + ((x2 - x1) - title_w) / 2
    draw.multiline_text((title_x, start_y), title, fill=TEXT, font=CARD_TITLE_FONT, spacing=8, align="center")
    if body:
        body_x = x1 + ((x2 - x1) - body_w) / 2
        draw.multiline_text((body_x, start_y + title_h + 18), body, fill=SUBTEXT, font=CARD_BODY_FONT, spacing=8, align="center")


def draw_arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]]) -> None:
    flat_points: list[int] = []
    for x, y in points:
        flat_points.extend([x, y])
    draw.line(flat_points, fill=ARROW, width=7)
    (x1, y1), (x2, y2) = points[-2], points[-1]
    if abs(x2 - x1) >= abs(y2 - y1):
        if x2 >= x1:
            arrow = [(x2, y2), (x2 - 20, y2 - 12), (x2 - 20, y2 + 12)]
        else:
            arrow = [(x2, y2), (x2 + 20, y2 - 12), (x2 + 20, y2 + 12)]
    else:
        if y2 >= y1:
            arrow = [(x2, y2), (x2 - 12, y2 - 20), (x2 + 12, y2 - 20)]
        else:
            arrow = [(x2, y2), (x2 - 12, y2 + 20), (x2 + 12, y2 + 20)]
    draw.polygon(arrow, fill=ARROW)


def build_fig_2_1() -> None:
    image, draw = make_canvas()
    draw_panel(draw, (90, 170, 290, 830), "知识源", fill=AMBER_FILL, outline=AMBER_OUTLINE)
    draw_card(draw, (115, 275, 265, 405), "图片资料", "页面 / 裁图", outline=AMBER_OUTLINE)
    draw_card(draw, (115, 595, 265, 725), "PDF 文档", "解析对象", outline=AMBER_OUTLINE)

    draw_panel(draw, (330, 130, 1270, 430), "图片桥接链路", fill=RED_FILL, outline=RED_OUTLINE)
    draw_card(draw, (370, 235, 545, 345), "知识图片", outline=RED_OUTLINE)
    draw_card(draw, (595, 235, 875, 345), "多模态模型", "生成语义描述", outline=RED_OUTLINE)
    draw_card(draw, (925, 235, 1105, 345), "语义描述文本", outline=RED_OUTLINE)
    draw_card(draw, (1155, 235, 1240, 345), "文本\n向量化", outline=RED_OUTLINE)

    draw_panel(draw, (330, 550, 1270, 850), "文档文本链路", fill=BLUE_FILL, outline=BLUE_OUTLINE)
    draw_card(draw, (370, 655, 545, 765), "PDF 文档", outline=BLUE_OUTLINE)
    draw_card(draw, (595, 655, 875, 765), "文本抽取", "与分块", outline=BLUE_OUTLINE)
    draw_card(draw, (925, 655, 1105, 765), "文本块", outline=BLUE_OUTLINE)
    draw_card(draw, (1155, 655, 1240, 765), "文本\n向量化", outline=BLUE_OUTLINE)

    draw_panel(draw, (1310, 130, 1710, 850), "统一检索与回答链路", fill=GREEN_FILL, outline=GREEN_OUTLINE)
    draw_card(draw, (1360, 190, 1660, 290), "统一查询入口", outline=GREEN_OUTLINE)
    draw_card(draw, (1360, 340, 1660, 450), "查询改写", "与向量化", outline=GREEN_OUTLINE)
    draw_cylinder(draw, (1350, 560, 1500, 820), "统一检索索引", "向量 + BM25\n元数据关联", outline=GREEN_OUTLINE)
    draw_card(draw, (1530, 585, 1660, 675), "混合检索", "结果融合", outline=GREEN_OUTLINE)
    draw_card(draw, (1530, 715, 1660, 815), "RAG 回答生成", "来源回溯", outline=GREEN_OUTLINE)

    draw_arrow(draw, [(265, 340), (370, 290)])
    draw_arrow(draw, [(265, 660), (370, 710)])
    draw_arrow(draw, [(545, 290), (595, 290)])
    draw_arrow(draw, [(875, 290), (925, 290)])
    draw_arrow(draw, [(1105, 290), (1155, 290)])
    draw_arrow(draw, [(545, 710), (595, 710)])
    draw_arrow(draw, [(875, 710), (925, 710)])
    draw_arrow(draw, [(1105, 710), (1155, 710)])
    draw_arrow(draw, [(1240, 290), (1290, 290), (1290, 645), (1350, 645)])
    draw_arrow(draw, [(1240, 710), (1290, 710), (1350, 710)])
    draw_arrow(draw, [(1510, 240), (1510, 340)])
    draw_arrow(draw, [(1510, 450), (1510, 560)])
    draw_arrow(draw, [(1500, 630), (1530, 630)])
    draw_arrow(draw, [(1595, 675), (1595, 715)])

    image.save(OUT_DIR / "fig2_1_semantic_bridging.png")


def build_fig_2_2() -> None:
    image, draw = make_canvas()
    draw_card(draw, (100, 420, 300, 560), "查询输入", "文本问题\n图像描述结果", outline=SLATE_OUTLINE)

    draw_panel(draw, (380, 160, 960, 410), "向量召回链路", fill=RED_FILL, outline=RED_OUTLINE)
    draw_card(draw, (435, 235, 625, 345), "查询向量化", outline=RED_OUTLINE)
    draw_card(draw, (690, 235, 900, 345), "向量检索", "Chroma 召回", outline=RED_OUTLINE)

    draw_panel(draw, (380, 590, 960, 840), "词项召回链路", fill=BLUE_FILL, outline=BLUE_OUTLINE)
    draw_card(draw, (435, 665, 625, 775), "词项分析", outline=BLUE_OUTLINE)
    draw_card(draw, (690, 665, 900, 775), "BM25 检索", "关键词补充召回", outline=BLUE_OUTLINE)

    draw_panel(draw, (1010, 300, 1320, 700), "结果融合", fill=PURPLE_FILL, outline=PURPLE_OUTLINE)
    draw_card(draw, (1060, 430, 1270, 560), "RRF 融合", "统一候选排序", outline=PURPLE_OUTLINE)

    draw_panel(draw, (1380, 300, 1710, 700), "重排与输出", fill=AMBER_FILL, outline=AMBER_OUTLINE)
    draw_card(draw, (1435, 370, 1655, 455), "重排模型", outline=AMBER_OUTLINE)
    draw_card(draw, (1435, 490, 1655, 575), "Top-K 结果", outline=AMBER_OUTLINE)
    draw_card(draw, (1435, 610, 1655, 695), "RAG 上下文", outline=AMBER_OUTLINE)

    draw_arrow(draw, [(300, 490), (380, 285), (435, 285)])
    draw_arrow(draw, [(300, 490), (380, 720), (435, 720)])
    draw_arrow(draw, [(625, 290), (690, 290)])
    draw_arrow(draw, [(625, 720), (690, 720)])
    draw_arrow(draw, [(900, 290), (1010, 470), (1060, 470)])
    draw_arrow(draw, [(900, 720), (1010, 520), (1060, 520)])
    draw_arrow(draw, [(1270, 495), (1380, 495), (1435, 412)])
    draw_arrow(draw, [(1545, 455), (1545, 490)])
    draw_arrow(draw, [(1545, 575), (1545, 610)])

    image.save(OUT_DIR / "fig2_2_hybrid_retrieval.png")


def build_fig_3_1() -> None:
    image, draw = make_canvas()
    draw_panel(draw, (90, 250, 300, 760), "资料输入", fill=AMBER_FILL, outline=AMBER_OUTLINE)
    draw_card(draw, (120, 330, 270, 450), "图片资料", "上传与补录", outline=AMBER_OUTLINE)
    draw_card(draw, (120, 550, 270, 670), "PDF 文档", "上传与解析", outline=AMBER_OUTLINE)

    draw_panel(draw, (360, 290, 610, 710), "知识入库", fill=RED_FILL, outline=RED_OUTLINE)
    draw_card(draw, (395, 395, 575, 595), "图片语义描述\n文档解析分块", "三存储同步", outline=RED_OUTLINE)

    draw_panel(draw, (680, 290, 900, 710), "统一索引", fill=BLUE_FILL, outline=BLUE_OUTLINE)
    draw_cylinder(draw, (725, 405, 855, 615), "检索索引", "向量 + BM25", outline=BLUE_OUTLINE)

    draw_panel(draw, (970, 290, 1190, 710), "检索使用", fill=PURPLE_FILL, outline=PURPLE_OUTLINE)
    draw_card(draw, (1010, 405, 1150, 615), "文本搜图\n图搜图\n片段召回", outline=PURPLE_OUTLINE)

    draw_panel(draw, (1260, 290, 1480, 710), "会话问答", fill=GREEN_FILL, outline=GREEN_OUTLINE)
    draw_card(draw, (1300, 405, 1440, 615), "RAG 回答\n来源回溯", outline=GREEN_OUTLINE)

    draw_panel(draw, (1550, 350, 1700, 650), "维护调整", fill=SLATE_FILL, outline=SLATE_OUTLINE)
    draw_card(draw, (1578, 425, 1672, 575), "重处理\n删除\n配置调整", outline=SLATE_OUTLINE)

    draw_arrow(draw, [(270, 390), (360, 500), (395, 500)])
    draw_arrow(draw, [(270, 610), (360, 520), (395, 520)])
    draw_arrow(draw, [(575, 500), (680, 500), (725, 500)])
    draw_arrow(draw, [(855, 510), (970, 510), (1010, 510)])
    draw_arrow(draw, [(1150, 510), (1260, 510), (1300, 510)])
    draw_arrow(draw, [(1440, 510), (1550, 510), (1578, 510)])
    draw_arrow(draw, [(1625, 575), (1625, 785), (500, 785), (500, 595)])

    image.save(OUT_DIR / "fig3_1_business_flow.png")


def build_fig_4_1() -> None:
    image, draw = make_canvas()
    draw_panel(draw, (90, 100, 1710, 230), "前端展示层", fill=BLUE_FILL, outline=BLUE_OUTLINE)
    draw_card(draw, (145, 145, 395, 205), "图片知识库页面", outline=BLUE_OUTLINE)
    draw_card(draw, (455, 145, 705, 205), "文档知识库页面", outline=BLUE_OUTLINE)
    draw_card(draw, (765, 145, 1015, 205), "检索页面", outline=BLUE_OUTLINE)
    draw_card(draw, (1075, 145, 1325, 205), "聊天页面", outline=BLUE_OUTLINE)
    draw_card(draw, (1385, 145, 1655, 205), "系统配置 / 状态反馈", outline=BLUE_OUTLINE)

    draw_panel(draw, (90, 280, 1710, 400), "接口服务层", fill=GREEN_FILL, outline=GREEN_OUTLINE)
    draw_card(draw, (145, 325, 1655, 385), "FastAPI 路由：上传、列表、检索、聊天、文档进度、配置管理", outline=GREEN_OUTLINE)

    draw_panel(draw, (90, 470, 520, 900), "业务编排层", fill=SLATE_FILL, outline=SLATE_OUTLINE)
    draw_card(draw, (130, 560, 480, 830), "图片管理\n文档解析调度\n会话管理\n状态同步", outline=SLATE_OUTLINE)

    draw_panel(draw, (590, 470, 1080, 900), "检索与语义处理层", fill=PURPLE_FILL, outline=PURPLE_OUTLINE)
    draw_card(draw, (640, 560, 1030, 830), "语义描述生成\n向量检索\nBM25 检索\nRRF 融合与重排\nRAG 上下文组织", outline=PURPLE_OUTLINE)

    draw_panel(draw, (1150, 470, 1710, 900), "数据存储层", fill=AMBER_FILL, outline=AMBER_OUTLINE)
    draw_card(draw, (1210, 560, 1660, 650), "SQLite 元数据", outline=AMBER_OUTLINE)
    draw_card(draw, (1210, 680, 1660, 770), "Chroma 向量索引", outline=AMBER_OUTLINE)
    draw_card(draw, (1210, 800, 1660, 890), "本地文件与解析结果", outline=AMBER_OUTLINE)

    draw_arrow(draw, [(900, 230), (900, 280), (900, 325)])
    draw_arrow(draw, [(900, 385), (900, 470), (805, 560)])
    draw_arrow(draw, [(900, 385), (300, 470), (300, 560)])
    draw_arrow(draw, [(900, 385), (1435, 470), (1435, 560)])
    draw_arrow(draw, [(480, 695), (590, 695), (640, 695)])
    draw_arrow(draw, [(1030, 695), (1150, 695), (1210, 695)])

    image.save(OUT_DIR / "fig4_1_overall_architecture.png")


def build_fig_4_2() -> None:
    image, draw = make_canvas()
    draw_panel(draw, (70, 280, 690, 720), "接收与落盘", fill=AMBER_FILL, outline=AMBER_OUTLINE)
    draw_panel(draw, (730, 280, 1070, 720), "语义化处理", fill=RED_FILL, outline=RED_OUTLINE)
    draw_panel(draw, (1110, 280, 1730, 720), "索引构建", fill=GREEN_FILL, outline=GREEN_OUTLINE)

    draw_card(draw, (110, 405, 300, 595), "图片上传", outline=AMBER_OUTLINE)
    draw_card(draw, (345, 405, 650, 595), "文件保存", "生成图片 ID", outline=AMBER_OUTLINE)
    draw_card(draw, (775, 405, 1025, 595), "语义描述生成", outline=RED_OUTLINE)
    draw_card(draw, (1155, 405, 1400, 595), "元数据与向量写入", outline=GREEN_OUTLINE)
    draw_card(draw, (1445, 405, 1690, 595), "BM25 更新", outline=GREEN_OUTLINE)

    draw_arrow(draw, [(300, 500), (345, 500)])
    draw_arrow(draw, [(650, 500), (730, 500), (775, 500)])
    draw_arrow(draw, [(1025, 500), (1110, 500), (1155, 500)])
    draw_arrow(draw, [(1400, 500), (1445, 500)])

    image.save(OUT_DIR / "fig4_2_image_ingestion_flow.png")


def build_fig_4_3() -> None:
    image, draw = make_canvas()
    draw_card(draw, (90, 400, 280, 600), "上传 PDF", outline=AMBER_OUTLINE)
    draw_card(draw, (340, 360, 620, 640), "创建文档记录", "返回文档 ID\n初始状态", outline=GREEN_OUTLINE)

    draw_panel(draw, (680, 180, 1160, 820), "后台异步解析", fill=PURPLE_FILL, outline=PURPLE_OUTLINE)
    draw_card(draw, (740, 275, 1100, 395), "文本抽取", outline=PURPLE_OUTLINE)
    draw_card(draw, (740, 445, 1100, 565), "句子感知分块", outline=PURPLE_OUTLINE)
    draw_card(draw, (740, 615, 1100, 735), "页面图像 / 表格资产", outline=PURPLE_OUTLINE)

    draw_card(draw, (1220, 360, 1490, 640), "知识同步", "写回 chunk、image\n状态与进度", outline=BLUE_OUTLINE)
    draw_card(draw, (1550, 400, 1710, 600), "前端轮询", "展示阶段与结果", outline=SLATE_OUTLINE)

    draw_arrow(draw, [(280, 500), (340, 500)])
    draw_arrow(draw, [(620, 500), (680, 500), (740, 500)])
    draw_arrow(draw, [(1100, 500), (1220, 500)])
    draw_arrow(draw, [(1490, 500), (1550, 500)])

    image.save(OUT_DIR / "fig4_3_document_ingestion_flow.png")


def build_fig_4_4() -> None:
    image, draw = make_canvas()
    draw_panel(draw, (90, 280, 300, 720), "用户输入", fill=AMBER_FILL, outline=AMBER_OUTLINE)
    draw_card(draw, (120, 360, 270, 480), "文本问题", outline=AMBER_OUTLINE)
    draw_card(draw, (120, 540, 270, 660), "附图请求", outline=AMBER_OUTLINE)

    draw_panel(draw, (380, 170, 700, 400), "文本入口", fill=GREEN_FILL, outline=GREEN_OUTLINE)
    draw_card(draw, (430, 250, 650, 340), "输入分析与分流", outline=GREEN_OUTLINE)

    draw_panel(draw, (380, 600, 700, 830), "图像桥接", fill=RED_FILL, outline=RED_OUTLINE)
    draw_card(draw, (430, 665, 650, 785), "生成语义描述", "复用文本检索链路", outline=RED_OUTLINE)

    draw_panel(draw, (780, 250, 1180, 750), "统一检索链路", fill=PURPLE_FILL, outline=PURPLE_OUTLINE)
    draw_card(draw, (840, 330, 1120, 410), "查询改写", outline=PURPLE_OUTLINE)
    draw_card(draw, (840, 460, 1120, 540), "向量 + BM25 双路召回", outline=PURPLE_OUTLINE)
    draw_card(draw, (840, 590, 1120, 670), "融合与重排", outline=PURPLE_OUTLINE)

    draw_panel(draw, (1260, 250, 1700, 750), "回答与回溯", fill=BLUE_FILL, outline=BLUE_OUTLINE)
    draw_card(draw, (1320, 330, 1640, 420), "组织上下文", outline=BLUE_OUTLINE)
    draw_card(draw, (1320, 470, 1640, 560), "生成回答", outline=BLUE_OUTLINE)
    draw_card(draw, (1320, 610, 1640, 700), "来源图片与检索步骤", outline=BLUE_OUTLINE)

    draw_arrow(draw, [(270, 420), (380, 285), (430, 285)])
    draw_arrow(draw, [(270, 600), (380, 725), (430, 725)])
    draw_arrow(draw, [(650, 285), (780, 380), (840, 380)])
    draw_arrow(draw, [(650, 725), (780, 630), (840, 630)])
    draw_arrow(draw, [(1120, 500), (1260, 500), (1320, 500)])
    draw_arrow(draw, [(1480, 420), (1480, 470)])
    draw_arrow(draw, [(1480, 560), (1480, 610)])

    image.save(OUT_DIR / "fig4_4_retrieval_qa_flow.png")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    build_fig_2_1()
    build_fig_2_2()
    build_fig_3_1()
    build_fig_4_1()
    build_fig_4_2()
    build_fig_4_3()
    build_fig_4_4()
    print(f"generated figures in: {OUT_DIR}")


if __name__ == "__main__":
    main()
