import sqlite3

import sys
from datetime import datetime, date, timedelta
import json
from enum import Enum

from PyQt5 import uic
from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
from PyQt5.QtWidgets import QApplication, QAbstractItemView
from PyQt5.QtWidgets import QMainWindow, QTableWidgetItem, QDialog
from PyQt5.QtWidgets import QPushButton, QLabel, QMessageBox
from PyQt5.QtGui import QPixmap


# Состояние выбранного места
class State(Enum):
    OFF = 0,
    ON = 1


# Кнопки под место в зале
class PlaceButton(QPushButton):
    def __init__(self, row, col, price):
        super().__init__()
        self.state = State.OFF
        self.row = row
        self.col = col
        self.price = price

    # Переключение состояния кнопки
    def switch(self):
        if self.state == State.OFF:
            self.state = State.ON
            self.setStyleSheet("background: #B5E61D;")
        else:
            self.state = State.OFF
            self.setStyleSheet("background: white;")

    # Ряд
    def get_row(self):
        return self.row

    # Место
    def get_col(self):
        return self.col

    # Состояние
    def get_state(self):
        return self.state

    # Цена
    def get_price(self):
        return self.price


# Диалог выбора мест
class TicketDialog(QDialog):
    def __init__(self, session):
        super().__init__()
        # Переменные
        self.session_id = session
        self.rows = None
        self.cols = None
        self.places = list()
        self.busy = list()
        self.price = dict()
        # Инициализация
        uic.loadUi('ui/ticket_dialog.ui', self)
        self.initDB()
        self.initUI()

    # Инициализация DB
    def initDB(self):
        self.conn = sqlite3.connect("db/cinema_db.sqlite3")

    # Инициализация UI
    def initUI(self):
        try:
            # Прочитаем информацию о сеансе
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT s.id, r.name as room, s.time, r.rows, r.cols,
                       f.title as film, c.title as cinema, s.price
                 FROM session s
                 LEFT JOIN room r ON s.room_id = r.id
                 LEFT JOIN cinema c ON r.cinema_id = c.id
                 LEFT JOIN film f ON s.film_id = f.id
                WHERE s.id = :ID
             """, {"ID": self.session_id})
            for row in cursor:
                self.infoSession.setText(f'Кинотеатр: {row[6]}, '
                                         f'Фильм: {row[5]}, '
                                         f'Зал: {row[1]}, '
                                         f'Сеанс: {row[2]}')
                self.rows = row[3]
                self.cols = row[4]
                self.price = json.loads(row[7])
            # Прочитаем информацию о купленных местах
            cursor.execute("""
                SELECT t.id, t.row, t.col
                 FROM ticket t
                WHERE t.session_id = :ID
             """, {"ID": self.session_id})
            for row in cursor:
                self.busy.append((row[1] - 1, row[2] - 1))

            # Создаем кнопки мест
            layout = self.placeSession
            for j in range(self.cols):
                col_lbl = QLabel(f'Место: {j + 1}')
                layout.addWidget(col_lbl, 0, j + 1)
            for i in range(self.rows):
                row_lbl = QLabel(f'Ряд: {i + 1}')
                layout.addWidget(row_lbl, i + 1, 0)
                for j in range(self.cols):
                    price = self.get_price(i + 1, j + 1)
                    btn = PlaceButton(i, j, price)
                    btn.setText(f'{price}р.')
                    if (i, j) in self.busy:
                        btn.setEnabled(False)
                    else:
                        btn.clicked.connect(self.place_click)
                    layout.addWidget(btn, i + 1, j + 1)
                    self.places.append(btn)
            # Размер кнопки 60*60, поэтому ячейку с отступами делаем 68px
            # Отступ слева для названий рядов = 70px
            # Отступ сверху для информации о фильме = 130px
            x = 68 * self.cols + 70
            y = 68 * self.rows + 130
            self.setMinimumSize(x, y)
            self.setMaximumSize(x, y)
        except Exception as e:
            print(e)

    # Получение цены для билета
    def get_price(self, row, col):
        # Ищем спец-цену для места
        price = self.price.get(f"{row}:{col}")
        if price is None:
            # Не нашли, ищем цену по ряду
            price = self.price.get(f"{row}:0")
            if price is None:
                # Не нашли, ищем цену по умолчанию
                price = self.price.get('0:0')
        return price

    # Нажатие на место
    def place_click(self):
        btn = self.sender()
        btn.switch()
        print(f'row={btn.get_row()} '
              f'col={btn.get_col()} '
              f'state={btn.get_state()}')

    # Возвращает выбранные места
    def get_selected(self):
        selected = list()
        for btn in self.places:
            if btn.get_state() == State.ON:
                selected.append((btn.get_row(),
                                 btn.get_col(),
                                 btn.get_price())
                                )
        return selected


# Печать заказа
class PrintDialog(QDialog):
    def __init__(self, order, selected, cinema, address,
                 film, day, time, room):
        super().__init__()
        # Переменные
        self.order = order
        self.selected = selected
        self.cinema = cinema
        self.address = address
        self.film = film
        self.day = day
        self.time = time
        self.room = room
        # Инициализация
        uic.loadUi('ui/print_dialog.ui', self)
        self.initDB()
        self.initUI()

    # Инициализация DB
    def initDB(self):
        self.conn = sqlite3.connect("db/cinema_db.sqlite3")

    # Инициализация UI
    def initUI(self):
        # Кнопки
        self.cancelButton.clicked.connect(self.cancel_click)
        self.printButton.clicked.connect(self.print_click)
        # Текст заказа
        self.orderInfo.append(f"<h1>Заказ №{self.order}</h1>")
        self.orderInfo.append(f"<p>"
                              f"<b>Кинотеатр:</b> {self.cinema}<br>"
                              f"<b>Адрес:</b> {self.address}<br>"
                              f"<b>Зал:</b> {self.room}<br>"
                              f"<b>Название фильма:</b> {self.film}<br>"
                              f"<b>Начало сеанса:</b> {self.day} {self.time}"
                              f"</p>")

        table = f"<table><tr><th>№ ряда</th><th>Место</th><th>Цена</th></tr>"
        itogo = 0
        for row in self.selected:
            table += f"<tr>" \
                     f"<td>{row[0] + 1}</td>" \
                     f"<td>{row[1] + 1}</td>" \
                     f"<td>{row[2]}р.</td>" \
                     f"</tr>"
            itogo += row[2]
        table += f"<tr><th>Итого</th><th>&nbsp;</th><th>{itogo}р.</th></tr>"
        table += f"</table>"
        self.orderInfo.append(table)

    # Закрытие окна
    def cancel_click(self):
        self.close()

    # Печать заказа
    def print_click(self):
        try:
            printer = QPrinter()
            dialog = QPrintDialog(printer)
            if dialog.exec() == QPrintDialog.Accepted:
                self.orderInfo.print(printer)
                print('print from if')
            print("print")
        except Exception as e:
            print(e)


# Главное окно
class MyWidget(QMainWindow):

    def __init__(self):
        super().__init__()
        # Переменные
        self.cinema = -1
        self.film = -1
        self.session = -1
        self.currentDate = date.today().strftime("%d.%m.%Y")
        self.currentGenre = 0
        self.cinema_name = None
        self.film_name = None
        self.address = None
        self.session_time = None
        self.room = None
        # Инициализация
        self.initDB()
        uic.loadUi('ui/main.ui', self)
        self.initUI()

    # Инициализация DB
    def initDB(self):
        self.conn = sqlite3.connect("db/cinema_db.sqlite3")
        self.update_db()

    # Инициализация UI
    def initUI(self):
        self.stack.setCurrentIndex(0)
        # Настраиваем сигналы кнопок
        self.backMain.setVisible(False)
        self.selectCinema.clicked.connect(self.select_cinema)
        self.selectFilm.clicked.connect(self.select_film)
        self.selectSession.clicked.connect(self.select_session)
        self.selectCinema.setEnabled(False)
        self.selectFilm.setEnabled(False)
        self.selectSession.setEnabled(False)
        self.backCinema.clicked.connect(self.back_cinema)
        self.backFilm.clicked.connect(self.back_film)
        # Настраиваем сигналы таблиц
        self.tableCinema.currentCellChanged.connect(self.click_cinema)
        self.tableFilm.currentCellChanged.connect(self.click_film)
        self.tableSession.currentCellChanged.connect(self.click_session)
        # Заполняем таблицу кинотеатров
        self.fill_cinema()
        # Настраиваем страницу фильмов:
        self.dateFilm.setDate(date.today())
        self.dateFilm.setMinimumDate(date.today())
        self.dateFilm.setMaximumDate(date.today() + timedelta(days=10))
        self.dateFilm.dateChanged.connect(self.date_film_change)
        # Заполняем comboBox
        self.fill_genre()
        self.cmbGenre.currentIndexChanged.connect(self.cmb_genre_change)
        # Делаем, чтобы при нажатии на ячейку выделялась вся строка
        self.tableCinema.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tableCinema.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableFilm.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tableFilm.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableSession.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tableSession.setSelectionBehavior(QAbstractItemView.SelectRows)

    # Изменение жанра
    def cmb_genre_change(self, index):
        self.currentGenre = index
        self.fill_film()

    # Изменение даты фильма
    def date_film_change(self):
        self.currentDate = self.dateFilm.date().toString("dd.MM.yyyy")
        self.fill_film()

    # Выбор кинотеатра и переход на следующую страницу
    def select_cinema(self):
        print('NEXT cinema')
        self.stack.setCurrentIndex(1)
        self.fill_film()

    # Выбор фильма и переход на следующую страницу
    def select_film(self):
        print('NEXT film')
        self.stack.setCurrentIndex(2)
        self.fill_session()
        self.fill_info_film()

    # Выбор сеанса и открытие диалога заказа билетов
    def select_session(self):
        print('NEXT session')
        dialog = TicketDialog(self.session)
        dialog.exec()
        result = dialog.result()
        if result == 1:
            selected = dialog.get_selected()
            if len(selected) > 0:
                # Определим сумму заказа
                price = 0
                for el in selected:
                    price += el[2]
                # Получим номер заказа
                order = self.new_order()
                # Сохраним данные
                self.save_order(self.session, order, selected)
                QMessageBox.information(self, "Заказ билетов",
                                        f"Забронировано {len(selected)} "
                                        f"билета(ов) на сумму {price} "
                                        f"рублей. Номер заказа: {order}")
                # Печатаем заказ
                print_dialog = PrintDialog(order, selected, self.cinema_name,
                                           self.address, self.film_name,
                                           self.currentDate, self.session_time,
                                           self.room)
                print_dialog.exec()
                self.stack.setCurrentIndex(0)
            else:
                QMessageBox.warning(self, "Заказ билетов",
                                    "Не выбрано ни одного места!")

    # Найдем номер последнего заказа
    def new_order(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT max(order_name) FROM ticket t
         """)
        for row in cursor:
            return row[0] + 1

    # Сохранение заказа
    def save_order(self, session_id, order_name, selected):
        cursor = self.conn.cursor()
        # Получим номер последней записи
        id = None
        cursor.execute("""
            SELECT max(id) FROM ticket t
         """)
        for row in cursor:
            id = row[0] + 1
        # Формируем массив с данными
        order = list()
        for row in selected:
            order.append((id,
                          session_id,
                          row[0] + 1,
                          row[1] + 1,
                          order_name,
                          row[2])
                         )
            id += 1
        # Вставляем записи в базу
        cursor.executemany("INSERT INTO ticket VALUES (?,?,?,?,?,?)", order)
        self.conn.commit()

    # Возврат на страницу выбора кинотеатра
    def back_cinema(self):
        print('BACK')
        self.stack.setCurrentIndex(0)

    # Возврат на страницу выбора фильма
    def back_film(self):
        print('BACK')
        self.stack.setCurrentIndex(1)

    # Заполнение таблицы кинотеатров
    def fill_cinema(self):
        cursor = self.conn.cursor()
        cursor.execute("""SELECT id, title, address, phone
                            FROM cinema
                            ORDER BY title
                       """)
        i = 0
        for row in cursor:
            self.tableCinema.setRowCount(i + 1)
            for j in range(3):
                self.tableCinema.setItem(i, j, QTableWidgetItem(str(row[j])))
            i += 1
        self.tableCinema.resizeColumnsToContents()

    # Заполнение таблицы фильмов
    def fill_film(self):
        self.infoFilm.clear()
        self.tableFilm.setRowCount(0)
        self.selectFilm.setEnabled(False)
        self.load_poster('empty.png')
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT f.id, f.title, g.title as genre, f.rating,
                            f.duration, c.title as cinema, f.description,
                            f.premiere, f.producer, f.country, f.release,
                            f.original, f.poster
             FROM session s
             LEFT JOIN room r ON s.room_id = r.id
             LEFT JOIN cinema c ON r.cinema_id = c.id
             LEFT JOIN film f ON s.film_id = f.id
             LEFT JOIN genre g ON f.genre_id = g.id
            WHERE s.date = ?
              and c.id = ?
              and (g.id = ? or 0 = ?)
            ORDER BY f.title
            """, (self.currentDate, self.cinema,
                  self.currentGenre, self.currentGenre))
        i = 0
        self.tableFilm.clearContents()
        for row in cursor:
            self.tableFilm.setRowCount(i + 1)
            for j in range(13):
                self.tableFilm.setItem(i, j, QTableWidgetItem(str(row[j])))
            i += 1
        self.tableFilm.resizeColumnsToContents()
        self.tableFilm.setColumnWidth(1, 500)
        for i in range(5, 13):
            self.tableFilm.hideColumn(i)

    # Заполнение таблицы сеансов
    def fill_session(self):
        self.tableSession.setRowCount(0)
        self.selectSession.setEnabled(False)
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT s.id, r.name as room, s.time,
                    cast(r.rows * r.cols - ifnull(z.cnt, 0) as text)
                        || ' из '
                        || cast(r.rows * r.cols as text) as empty,
                    f.title as film, c.title as cinema
             FROM session s
             LEFT JOIN room r ON s.room_id = r.id
             LEFT JOIN cinema c ON r.cinema_id = c.id
             LEFT JOIN film f ON s.film_id = f.id
             LEFT JOIN (
                SELECT t.session_id, count(*) as cnt
                  FROM ticket t
                 GROUP BY t.session_id) z ON s.id = z.session_id
            WHERE s.date = ?
              and c.id = ?
              and f.id = ?
            """, (self.currentDate, self.cinema, self.film))
        i = 0
        self.tableSession.clearContents()
        for row in cursor:
            self.tableSession.setRowCount(i + 1)
            for j in range(4):
                self.tableSession.setItem(i, j, QTableWidgetItem(str(row[j])))
            i += 1
        self.tableSession.resizeColumnsToContents()
        self.tableSession.setColumnWidth(1, 300)

    # Заполнение lineEdit
    def fill_info_film(self):
        self.lineFilmInfo.setText(f'Кинотеатр: {self.cinema_name}, '
                                  f'Фильм: {self.film_name}')

    # Заполнение comboBox
    def fill_genre(self):
        cursor = self.conn.cursor()
        cursor.execute("""SELECT title
                            FROM genre
                            ORDER BY id
                       """)
        self.cmbGenre.addItem('---== ВСЕ ==---')
        for row in cursor:
            self.cmbGenre.addItem(row[0])

    # Выбор кинотеатра в таблице
    def click_cinema(self, r, c, pr, pc):
        if self.tableCinema.item(0, 0) is None:
            return
        if r >= 0 and c >= 0:
            print(f'cinema: {r}, {c}')
            # self.tableCinema.selectRow(r)
            self.cinema = int(self.tableCinema.item(r, 0).text())
            self.cinema_name = self.tableCinema.item(r, 1).text()
            self.address = self.tableCinema.item(r, 2).text()
            self.selectCinema.setEnabled(True)

    # Выбор фильма в таблице
    def click_film(self, r, c, pr, pc):
        if self.tableFilm.item(0, 0) is None:
            return
        if r >= 0 and c >= 0:
            print(f'film: {r}, {c}')
            self.film = int(self.tableFilm.item(r, 0).text())
            self.film_name = self.tableFilm.item(r, 1).text()
            self.selectFilm.setEnabled(True)
            self.infoFilm.clear()
            self.infoFilm.append(f"<b>Кинотеатр:</b> "
                                 f"{self.tableFilm.item(r, 5).text()}")
            self.infoFilm.append(f"<b>О фильме:</b><br>"
                                 f"{self.tableFilm.item(r, 6).text()}")
            self.infoFilm.append(f"<b>Премьера:</b> "
                                 f"{self.tableFilm.item(r, 7).text()}")
            self.infoFilm.append(f"<b>Продюсер:</b> "
                                 f"{self.tableFilm.item(r, 8).text()}")
            self.infoFilm.append(f"<b>Время:</b> "
                                 f"{self.tableFilm.item(r, 4).text()} мин")
            self.infoFilm.append(f"<b>Страна:</b> "
                                 f"{self.tableFilm.item(r, 9).text()}")
            self.infoFilm.append(f"<b>Год производства:</b> "
                                 f"{self.tableFilm.item(r, 10).text()}")
            self.infoFilm.append(f"<b>Оригинальное название:</b> "
                                 f"{self.tableFilm.item(r, 11).text()}")
            self.load_poster(self.tableFilm.item(r, 12).text())

    # Выбор сеанса в таблице
    def click_session(self, r, c, pr, pc):
        if self.tableSession.item(0, 0) is None:
            return
        if r >= 0 and c >= 0:
            print(f'session: {r}, {c}')
            self.session = int(self.tableSession.item(r, 0).text())
            self.room = self.tableSession.item(r, 1).text()
            self.session_time = self.tableSession.item(r, 2).text()
            self.selectSession.setEnabled(True)

    # Загрузка постера
    def load_poster(self, file_name):
        img = QPixmap(f'images/{file_name}')
        self.poster.setPixmap(img)

    # Обновление дат сеансов.
    def update_db(self):
        cursor = self.conn.cursor()
        cursor.execute("""
                        SELECT id, date
                         FROM session s
                        ORDER BY date
                        """)
        today = datetime.today()
        delta = None
        for row in cursor:
            if delta is None:
                delta = today - datetime.strptime(row[1], "%d.%m.%Y")
            new_date = datetime.strptime(row[1], "%d.%m.%Y") + delta
            update = self.conn.cursor()
            update.execute("""
                UPDATE session SET date = ?
                WHERE id = ?
                """, (new_date.strftime("%d.%m.%Y"), row[0]))
        self.conn.commit()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet('''
        QLineEdit {
            border: 1px solid gray;
            padding: 5px;
        }
        PlaceButton {
            border: 1px solid gray;
            background: white;
            font-size: 10pt;
            font-weight: bold;
            height: 40px;
            width: 40px;
            padding: 10px;
        }
        PlaceButton::disabled {
            background: #FFAEC9;
        }
    ''')
    ex = MyWidget()
    ex.show()
    sys.exit(app.exec())
