import shutil
from io import BytesIO
import os
from logging import getLogger, debug
from dataclasses import dataclass, astuple, InitVar
from pyqrcode import create as create_qrcode
from pathlib import Path
import qrcode.image.svg

from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Image
from sqlalchemy import MetaData, Table, create_engine

from fpiweb.models import Box
from FPIDjango.private import settings_private

logger = getLogger('fpiweb')

# Combined path factory, fixes white space that may occur when zooming
factory = qrcode.image.svg.SvgPathImage


def get_qr_code_svg(data_string, include_xml_declaration=False):
    img = qrcode.make(data_string, image_factory=factory)
    # move to scans??
    shutil.move(img, 'scans')

    with BytesIO() as bytes_out:
        img.save(bytes_out, kind='SVG')

        some_bytes = bytes_out.getvalue()
        svg = some_bytes.decode('utf-8')

        if not include_xml_declaration:
            svg = svg.split('?>\n')[-1]
        return svg


log = None


@dataclass()
class Point:
    """
    Horizontal (x) and vertical (y) coordinate.
    """
    x: int
    y: int


LABEL_SIZE: Point = Point(144, 144)  # 2 in x 2 in
LABEL_MARGIN: Point = Point(18, 18)  # 1/4 in x 1/4 in
BACKGROUND_SIZE: Point = Point(
    LABEL_SIZE.x + (LABEL_MARGIN.x * 2),
    LABEL_SIZE.y + (LABEL_MARGIN.y * 2))
PAGE_OFFSET: Point = Point(36, 36)  # 1/2 in x 1/2 in
TITLE_ADJUSTMENT: Point = Point(+20, -9)


@dataclass
class LabelPosition:
    """
    Container for measurements for one label.

    All measurements are in points.
    x denotes horizontal measurement
    y denotes vertical
    origin is in lower left corner
    label is assumed to be 2 in x 2 in ( 144 pt x 144 pt)
    """
    page_offset: InitVar[Point]
    lower_left_offset: Point = Point(0, 0)
    lower_right_offset: Point = Point(0, 0)
    upper_left_offset: Point = Point(0, 0)
    upper_right_offset: Point = Point(0, 0)
    offset_on_page: Point = Point(0, 0)
    image_start: Point = Point(0, 0)
    title_start: Point = Point(0, 0)

    def __post_init__(self, page_offset: Point):
        """
        Adjust offsets based on offset_on_page.

        :param page_offset: offset (in points) from the lower left corner
        :return:
        """
        self.offset_on_page = page_offset

        x: int = page_offset.x
        y: int = page_offset.y
        offset: Point = Point(x, y)
        self.lower_left_offset = offset

        x = page_offset.x + BACKGROUND_SIZE.x
        y = page_offset.y
        offset: Point = Point(x, y)
        self.lower_right_offset = offset

        x = page_offset.x
        y = page_offset.y + BACKGROUND_SIZE.y
        offset: Point = Point(x, y)
        self.upper_left_offset = offset

        x = page_offset.x + BACKGROUND_SIZE.x
        y = page_offset.y + BACKGROUND_SIZE.y
        offset: Point = Point(x, y)
        self.upper_right_offset = offset

        x = self.lower_left_offset.x + LABEL_MARGIN.x
        y = self.lower_left_offset.y + LABEL_MARGIN.y
        self.image_start: Point = Point(x, y)

        # title placement calculation
        x = self.upper_left_offset.x + (LABEL_SIZE.x // 2)
        y = self.upper_left_offset.y - LABEL_MARGIN.y
        self.title_start: Point = Point(x, y)
        return


class QRCodePrinter(object):

    def __init__(self, workdir: Path):
        self.working_dir: Path = None
        self.url_prefix: str = ''
        self.box_start: int = 0
        self.label_count: int = 0
        self.output_file: str = ''
        self.full_path: Path = None
        self.pdf: Canvas = None

        # width and height are in points (1/72 inch)
        self.width: int = None
        self.height: int = None

        # database connection information
        self.con = None
        self.meta: MetaData = None
        self.box: Table = None

        # label locations on the page
        self.label_locations: list(LabelPosition) = list()
        self.compute_box_dimensions()

        # set this to the last position in the list to force a new page
        self.next_pos: int = len(self.label_locations)

        # use the page number to control first page handling
        self.page_number: int = 0

        if not workdir is None and workdir.is_dir():
            self.working_dir = workdir
        return

    def run_QRPrt(self, parameters: dict):
        """
        Top method for running Run the QR code printer..

        :param parameters: dictionary of command line arguments
        :return:
        """
        parm_dict = parameters
        self.url_prefix: str = parm_dict['--prefix'].strip('\'"')
        self.box_start: int = int(parm_dict['--start'])
        self.label_count: int = int(parm_dict['--count'])
        self.output_file: str = parm_dict['--output']
        if (not isinstance(self.box_start, int)) or \
                self.box_start <= 0:
            raise ValueError('Box start must be a positive integer')
        if (not isinstance(self.label_count, int)) or \
                self.label_count <= 0:
            raise ValueError('Label count must be a positive integer')
        full_path = Path('/home/capstonetest/PycharmProjects/Food-Pantry-Inventory/scans') / self.output_file
        if full_path.exists():
            raise ValueError('File already exists')
        else:
            self.full_path = full_path
        debug(
            f'Parameters validated: pfx: {self.url_prefix}, '
            f'start: {self.box_start}, '
            f'count: {self.label_count}, '
            f'file: {self.output_file}'
        )

        self.connect_to_generate_labels()

    def connect_to_generate_labels(self):
        """
        Connect to the database and generate labels.
        :return:
        """
        # establish access to the database
        self.con, self.meta = self.connect(
            user=settings_private.DB_USER,
            password=settings_private.DB_PSWD,
            db=settings_private.DB_NAME,
            host=settings_private.DB_HOST,
            port=settings_private.DB_PORT
        )

        # establish access to the box table
        self.box = Table(
            'fpiweb_box',
            self.meta,
            autoload=True,
            autoload_with=self.con)

        self.generate_label_pdf()
        # self.con.close()

    def connect(self, user, password, db, host='localhost', port=5432):
        """
        Establish a connection to the desired PostgreSQL database.

        :param user:
        :param password:
        :param db:
        :param host:
        :param port:
        :return:
        """

        # We connect with the help of the PostgreSQL URL
        # postgresql://federer:grandestslam@localhost:5432/tennis
        url = f'postgresql://{user}:{password}@{host}:{port}/{db}'

        # The return value of create_engine() is our connection object
        con = create_engine(url, client_encoding='utf8')
        # We then bind the connection to MetaData()
        meta = MetaData(bind=con)
        return con, meta

    def generate_label_pdf(self):
        """
        Generate the pdf file with the requested labels in it.
        :return:
        """
        self.initialize_pdf_file()
        self.fill_pdf_pages()
        self.finalize_pdf_file()

    def initialize_pdf_file(self, buffer):
        """
        Prepare to scribble on a new pdf file.

        :param buffer:  May be a string with a filename or a BytesIO or other
            File-like object

        """
        self.pdf: Canvas(buffer, pagesize=letter)
        self.width, self.height = letter

    def compute_box_dimensions(self):
        """
        Compute the dimensions and bounding boxes for each label on the page.
        :return:
        """
        vertical_start = (BACKGROUND_SIZE.y * 3) + PAGE_OFFSET.y
        horizontal_stop = (BACKGROUND_SIZE.x * 3) + PAGE_OFFSET.x - 1
        for vertical_position in range(vertical_start, -1,
                                       -BACKGROUND_SIZE.y):
            for horizontal_position in range(PAGE_OFFSET.x,
                                             horizontal_stop,
                                             BACKGROUND_SIZE.x):
                new_label = LabelPosition(Point(horizontal_position,
                                                vertical_position))
                self.label_locations.append(new_label)
        return

    @staticmethod
    def get_box_numbers(start, count) -> (str, int):
        next_box_number = start
        available_count = 0
        while available_count < count:
            box_label = f'BOX{next_box_number:05}'
            logger.debug(f'Attempting to get {box_label}')
            if Box.objects.filter(box_number=box_label).exists():
                next_box_number += 1
                continue
            available_count += 1
            logger.debug(f'{box_label} not found - using for label')
            yield box_label, next_box_number
            next_box_number += 1

    def get_next_box_url(self, starting_number, count) -> (str, str):
        """
        Build the URL for the next box.
        :return:
        """
        for label, box_number in self.get_box_numbers(
                starting_number,
                count
        ):
            logger.debug(f'Got {label}, {box_number}')
            url = f"{self.url_prefix}{box_number:05}"
            yield url, label
            # shutil.move(label, 'scans')

    def get_next_qr_img(self, starting_number, count) -> (str, str):
        """
        Build the QR image for the next box label.

        :return: a QR code image ready to print
        """
        # scans_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        files = []
        for url, label in self.get_next_box_url(starting_number, count):
            label_file_name = f'{label}.png'
            qr = create_qrcode(url)
            qr.png(label_file_name, scale=5)
            files.append(label_file_name)
        for file in files:
            shutil.move(file, '/home/capstonetest/PycharmProjects/Food-Pantry-Inventory/scans',
                        copy_function=shutil.copytree)


            yield label_file_name, label

    def fill_pdf_pages(self, starting_number, count):
        # # draw lines around the boxes that will be filled with labels
        # self.draw_boxes_on_page()
        # # self.pdf.setFillColorRGB(1, 0, 1)
        # # self.pdf.rect(2*inch, 2*inch, 2*inch, 2*inch, fill=1)
        for label_file, label_name in self.get_next_qr_img(starting_number, count):
            debug(f'Got {label_file}')
            if self.next_pos >= len(self.label_locations) - 1:
                self.finish_page()
                self.next_pos = 0
            else:
                self.next_pos += 1
            self.draw_bounding_box(self.next_pos)
            self.place_label(label_file, label_name, self.next_pos)
        self.finish_page()
        return

    def finalize_pdf_file(self):
        self.pdf.save()
        return

    def print(self, starting_number, count, buffer):
        self.initialize_pdf_file(buffer)
        self.fill_pdf_pages(starting_number, count)
        self.finalize_pdf_file()

    def finish_page(self):
        if self.page_number > 0:
            self.pdf.showPage()
        self.page_number += 1

    def place_label(self, file_name: str, label_name: str, pos: int):
        """
        Place the label in the appropriate location on the page.

        :param file_name:
        :param label_name:
        :param pos:
        :return:
        """
        box_info = self.label_locations[pos]

        # place image on page
        im = Image(file_name, LABEL_SIZE.x, LABEL_SIZE.y)
        im.drawOn(self.pdf, box_info.image_start.x, box_info.image_start.y)

        # place title above image
        self.pdf.setFont('Helvetica-Bold', 12)
        self.pdf.drawCentredString(
            box_info.title_start.x + TITLE_ADJUSTMENT.x,
            box_info.title_start.y + TITLE_ADJUSTMENT.y,
            label_name
        )

    def draw_bounding_box(self, label_pos: int):
        """
        Draw a bounding box around the specified label.

        :param label_pos: position in the labels locations list.
        :return:
        """
        self.pdf = Canvas(str(self.full_path), pagesize=letter)
        self.width, self.height = letter

        box_info = self.label_locations[label_pos]

        self.pdf.line(box_info.upper_left_offset.x,
                      box_info.upper_left_offset.y,
                      box_info.upper_right_offset.x,
                      box_info.upper_right_offset.y)

        self.pdf.line(box_info.upper_right_offset.x,
                      box_info.upper_right_offset.y,
                      box_info.lower_right_offset.x,
                      box_info.lower_right_offset.y)

        self.pdf.line(box_info.lower_right_offset.x,
                      box_info.lower_right_offset.y,
                      box_info.lower_left_offset.x,
                      box_info.lower_left_offset.y)

        self.pdf.line(box_info.lower_left_offset.x,
                      box_info.lower_left_offset.y,
                      box_info.upper_left_offset.x,
                      box_info.upper_left_offset.y)
