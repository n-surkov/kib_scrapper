"""
Классы для парсинга каталогов КиБ через селениум
"""
import time
import pickle
import os
import pandas as pd
import numpy as np
from typing import List

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

DEFAULT_DELAY = 10
KIB_LINK = "https://krasnoeibeloe.ru/"
KIB_CATALOG_LINK = "https://krasnoeibeloe.ru/catalog/"


class LocalCatalogItems:
    """
    Класс хранения продуктов каталога
    """
    dataframe_columns = ['region', 'city', 'address',
                         'id', 'pic_url', 'name', 'category', 'link',
                         'price', 'all_prices']

    def __init__(self, region: str, city: str, address: str):
        """

        Parameters
        ----------
        region: str, название региона
        city: str, название города
        address: str, адрес магазина
        """
        self.region = region
        self.city = city
        self.address = address

        self.items_list = []

    def add_element(self, element: webdriver, category: str):
        """
        Добавление продукта в каталог

        Parameters
        ----------
        element: WebDrver, элемент, относящийся к продукту
        category: str, категория продукта
        """
        item_props = dict()
        item_props['category'] = category
        item_props['region'] = self.region
        item_props['city'] = self.city
        item_props['address'] = self.address

        item_props['id'] = element.get_attribute('id')
        item_props['pic_url'] = element.find_element_by_tag_name('img').get_attribute('src')
        item_props['name'] = element.find_element_by_class_name('product_item_name').text
        item_props['link'] = (
            element.find_element_by_class_name('product_item_name')
            .find_element_by_tag_name('a').get_attribute('href')
        )

        item_props['price'] = None
        item_props['all_prices'] = []
        try:
            prices = element.find_element_by_class_name('i_price').find_elements_by_tag_name('div')
            for price in prices:
                style = price.get_attribute('style')
                if not style:
                    item_props['price'] = price.text
                    item_props['all_prices'].append(price.text.strip())
                else:
                    item_props['all_prices'].append(price.text.strip())
        except:
            pass

        self.items_list.append(item_props)

    def import_from_df(self, df):
        """
        Импорт каталога из ранее сохранённой csv-шки

        Parameters
        ----------
        df: pd.DataFrame, датафрейм, выкачанный из csv
        """
        for row in df.iterrows():
            item_props = {}
            for col in self.dataframe_columns:
                item_props[col] = str(row[1][col])
            self.items_list.append(item_props)
        self.address = row[1]['address']

    def get_dataframe(self):
        """
        Формирования датафрейма из элементов каталога

        Returns
        -------
        df: pd.DataFrame, датафрейм, содержащий информацию о продуктах
        """
        data = []
        for item in self.items_list:
            data.append([item['region'], item['city'], item['address'],
                         item['id'].split('_')[-1], item['pic_url'], item['name'],
                         item['category'], item['link'], item['price'], '; '.join(item['all_prices'])])
        df = pd.DataFrame(data, columns=self.dataframe_columns)

        return df

    def __repr__(self):
        return str(self.__dict__)


class Scroller:
    """
    Класс скроллера для переключения между страницами
    """
    def __init__(self, driver: webdriver):
        """
        Вытаскивание нужных кнопок для переключения между страницами

        Parameters
        ----------
        driver: WebDriver, запущенный драйвер
        """
        self.driver = driver
        try:
            self.scroller = (
                WebDriverWait(self.driver, DEFAULT_DELAY)
                .until(EC.presence_of_element_located((By.CLASS_NAME, 'bl_pagination')))
            )
            try:
                self.next_page_button = self.scroller.find_element_by_class_name('pag_arrow_right')
                self.active_page_num = int(self.scroller.find_element_by_class_name('active').text)
                buttons = self.scroller.find_elements_by_tag_name('li')
                max_page_num = 0
                for b in buttons:
                    try:
                        p = int(b.text)
                        if p > max_page_num:
                            max_page_num = p
                    except:
                        continue
                self.max_page_num = max_page_num
            except:
                self.next_page_button = None
                self.max_page_num = 1
                self.active_page_num = 1
        except TimeoutException:
            print("Не удалось загрузить каталог")
            self.scroller = None
            self.next_page_button = None
            self.max_page_num = 1
            self.active_page_num = 1

    def next_page(self):
        """
        Переключение на следующую страницу каталога
        """
        if self.scroller is None or self.next_page_button is None:
            return False
        if self.active_page_num < self.max_page_num:
            self.next_page_button.click()
            time.sleep(3)
            try:
                scroller = (
                    WebDriverWait(self.driver, DEFAULT_DELAY)
                    .until(EC.presence_of_element_located((By.CLASS_NAME, 'bl_pagination')))
                )
            except TimeoutException:
                raise TimeoutException("Не удалось переключиться на следующую страницу каталога.")

            active_page_num = int(scroller.find_element_by_class_name('active').text)
            if active_page_num != self.active_page_num:
                self.active_page_num = active_page_num
                return True
            else:
                return False
        else:
            return False


class ShopSelector:
    """
    Класс для операций с магазинами
    """
    def __init__(self, driver: webdriver):
        """

        Parameters
        ----------
        driver: WebDriver
        """
        self.driver = driver

        self.shop_selector_button = None
        self.shop_selector = None
        self.region_selector = None
        self.city_selector = None
        self.current_url = None

        self.update_state()

    def update_state(self):
        try:
            self.shop_selector_button = (
                WebDriverWait(self.driver, DEFAULT_DELAY)
                .until(EC.presence_of_element_located((By.CLASS_NAME, 'header_top_left')))
            )
        except TimeoutException:
            raise TimeoutException("Не удалось найти кнопку выбора магазина.")

        self.current_url = self.driver.current_url

    def open_shop_selection_window(self):
        """
        Открытие окна выбора магазинов.

        В атрибут класса `shop_selector` кладётся окно выбора магазина
        """
        self.shop_selector_button.click()

        try:
            # Форма выбора магазина
            self.shop_selector = (
                WebDriverWait(self.driver, DEFAULT_DELAY)
                .until(EC.presence_of_element_located((By.ID, 'shop_select_form')))
            )

            # Селекторы выбора региона и города
            _ = (
                WebDriverWait(self.driver, DEFAULT_DELAY)
                .until(EC.presence_of_element_located((By.CLASS_NAME, 'item_select_city')))
            )
            selectors = self.shop_selector.find_elements_by_class_name('item_select_city')
            region_selector, city_selector = None, None
            for selector in selectors:
                if selector.find_elements_by_name('region'):
                    region_selector = selector
                elif selector.find_elements_by_name('city'):
                    city_selector = selector
            if region_selector is None or city_selector is None:
                raise ValueError('Не удалось найти селекторы города или региона')

            self.region_selector = region_selector
            self.city_selector = city_selector

        except TimeoutException:
            raise TimeoutException("Загрузить форму выбора магазина.")

    def parse_shop_list(self, regions: List[str] = []) -> dict:
        """
        Парсим список всех магазинов

        Parameters
        ----------
        regions: Optional[List[str]] (default=[]), список регионов, по которым нужно выкачать список магазинов.
            По-дефолту -- все регионы

        Returns
        -------
        shop_list: dict, {'регион': {'город': [адрес1, адрес2,...]}}

        """
        # Открываем окно выбора магазина
        self.update_state()
        self.open_shop_selection_window()

        # Выкачиваем список регионов
        region_list = []
        for i, el in enumerate(self.region_selector.find_elements_by_class_name('option')):
            region = el.text.strip()
            if region in regions or not regions:
                if region not in region_list:
                    region_list.append(region)

        # Проходимся по каждому региону и выкачиваем список городов и магазинов
        shop_list = {}
        for reg in region_list:
            self.region_selector.find_element_by_tag_name('input').send_keys(reg + Keys.ENTER)
            time.sleep(1)

            cities_shops = {}
            # Проходимся по каждому городу
            city_list = [el.text.strip() for el in self.city_selector.find_elements_by_class_name('option')]
            for city in city_list:
                # Выбираем город
                if city in cities_shops.keys():
                    continue
                self.city_selector.find_element_by_tag_name('input').send_keys(city + Keys.ENTER)
                # Скачиваем список магазинов
                shop_adresses = []
                shops = self.shop_selector.find_elements_by_class_name('shop_list_row')
                for shop in shops:
                    shop_adresses.append(shop.find_element_by_class_name('shop_list_row__title').text.strip())
                if shop_adresses:
                    cities_shops[city] = shop_adresses
            if cities_shops:
                shop_list[reg] = cities_shops

        self.driver.get(self.current_url)
        time.sleep(5)
        return shop_list

    def select_shop(self, region: str, city: str, address: str):
        """
        Выбор магазина

        Parameters
        ----------
        region: str, регион
        city: str, город
        address: str, адрес магазина
        """
        # Открываем окно выбора магазина
        self.update_state()
        self.open_shop_selection_window()

        # Выбираем регион и город
        self.region_selector.find_element_by_tag_name('input').send_keys(region + Keys.ENTER)
        time.sleep(1)
        self.city_selector.find_element_by_tag_name('input').send_keys(city + Keys.ENTER)
        time.sleep(1)

        # Выбираем магазин
        shops = self.shop_selector.find_elements_by_class_name('shop_list_row')
        if shops:
            for shop in shops:
                if address in shop.text:
                    shop_radio = shop.find_element_by_class_name('radio')
                    shop_radio.click()
                    break
            else:
                shop_radio = shop.find_element_by_class_name('radio')
                shop_radio.click()
        else:
            raise KeyError(f'В регионе {region} города {city} нет магазинов')

        # Подтверждаем выбор
        time.sleep(5)
        try:
            submit_button = (
                WebDriverWait(self.driver, DEFAULT_DELAY)
                .until(EC.presence_of_element_located((By.NAME, 'submit')))
            )
            submit_button.click()
        except TimeoutException:
            raise TimeoutException("Не получилось подтвердить выбор магазина")
        time.sleep(3)


class KibCatalog:
    def __init__(self, driver: webdriver, save_path: str = './parsed_data',
                 kib_login: str = None, kib_password: str = None,
                 regions: List[str] = []):
        """Переход на КиБ и логин

        Parameters
        ----------
        driver: WebDriver
        save_path: str, путь, куда будут сохраняться результаты парсинга.
        kib_login: str, логин для захода в ЛК
        kib_password: str, пароль для захода в ЛК
        regions: List[str], список регионов для парсинга
        """
        # Задание атрибутов
        self.kib_link = KIB_LINK
        self.catalog_link = KIB_CATALOG_LINK

        self.kib_login = kib_login
        self.kib_password = kib_password
        self.data_folder = save_path

        # Переход на сайт КиБ
        self.driver = driver
        self.driver.get(self.kib_link)
        time.sleep(5)
        self.close_popup_age()
        self.shop_selector = ShopSelector(driver)

        # Чтение списка магазинов
        path = os.path.join(self.data_folder, 'shops_info.pickle')
        if os.path.exists(path):
            with open(path, 'rb') as fo:
                self.shop_list = pickle.load(fo)
        else:
            self.shop_list = self.shop_selector.parse_shop_list(regions)
            with open(path, 'wb') as fo:
                pickle.dump(self.shop_list, fo)
        self.shops_for_parsing = self.get_proper_shops()

        # Логинимся
        if self.kib_login is None or self.kib_password is None:
            print('Невозможно зайти в ЛК, так как не были переданы лог и пасс')
        else:
            self.login()

    def parse_all_catalogs(self, categories: List[str] = []):
        """
        Парсинг всех крупных городов с сайта КиБ и запись их в атрибут класса catalogs.

        Parameters
        ----------
        categories: Optional[List[str]] (default=[]), Список категорий для парсинга. По дефолту -- все категории.
        """
        # Ищем уже спаршенные
        files = os.listdir(self.data_folder)
        saved_regions = {}
        for file in files:
            name, ext = os.path.splitext(file)
            if ext != '.csv':
                continue
            splited_name = name.split('_')
            saved_regions[splited_name[-2]] = {
                splited_name[-1]: os.path.join(self.data_folder, file)
            }
        print(saved_regions)

        # Парсим
        self.catalogs = []
        for region, cities in self.shops_for_parsing.items():
            for city, shops in cities.items():
                print(f'parse {region} -- {city}')
                try:
                    saved_cities = list(saved_regions[region].keys())
                except:
                    saved_cities = []
                if city in saved_cities:
                    path = saved_regions[region][city]
                    df = pd.read_csv(path)
                    local_items = LocalCatalogItems(region, city, '')
                    local_items.import_from_df(df)
                    self.catalogs.append(local_items)
                    print(f'data loaded from file {path}')
                else:
                    address = np.random.choice(shops)
                    local_items = self.parse_catalog(region, city, address, categories)
                    self.catalogs.append(local_items)

                    df = local_items.get_dataframe()
                    path = os.path.join(self.data_folder, f'kib_catalog_{region}_{city}.csv')
                    df.to_csv(path, index=False)
                    print(f'data saved to file {path}')

    def close_popup_age(self):
        """
        Закрытие всплывающего окна с возрастом.
        Есть нюанс -- оно появляется только если сделать окно браузера активным.
        """
        popup = self.driver.find_elements_by_id('age_popup_container')
        if popup:
            try:
                popup[0].find_element_by_link_text('Да').click()
            except:
                pass
        time.sleep(2)

    def login(self):
        """
        Заходим в КиБ, заходим в личный кабинет
        """
        self.close_popup_age()

        # Заходим в ЛК
        lk_link = self.driver.find_element_by_class_name('bl_top_lk').find_element_by_tag_name('a').get_attribute('href')
        self.driver.get(lk_link)

        log_block = self.driver.find_element_by_name('phone')
        log_block.send_keys(self.kib_login)
        pas_block = self.driver.find_element_by_name('USER_PASSWORD')
        pas_block.send_keys(self.kib_password)
        login_button = self.driver.find_element_by_name('Login')
        login_button.click()
        time.sleep(3)

        # Переходим обратно в каталог
        self.driver.get(self.kib_link)
        time.sleep(3)

    def get_proper_shops(self, city_shops_cnt_default: int = 20):
        """
        Отбор магазинов для парсинга.

        Если парсить все магазины, то на это может уйти очень немало времени. Поэтому отбираются только те города,
        в которых магазинов больше, чем city_shops_cnt_default.

        Parameters
        ----------
        city_shops_cnt_default: Optional[int], пороговое значение количества магазинов

        Returns
        -------
        proper_shops: dict, отобранные для парсинга города {'регион': {'город': [адрес1, адрес2,...]}}

        """
        # Выбираем только те города, где есть приличное количество магазинов
        proper_shops = {}
        for reg, sl in self.shop_list.items():
            proper_shops[reg] = {}
            curr_city = ''
            curr_sc = 0
            for city, shops in sl.items():
                sc = len(shops)
                if sc >= city_shops_cnt_default:
                    proper_shops[reg][city] = shops
                elif sc > curr_sc:
                    curr_city = city
                    curr_sc = sc
            if not proper_shops[reg] and curr_city:
                proper_shops[reg][city] = shops

        return proper_shops

    def parse_catalog(self, region: str, city: str, address: str, categories_needed: List[str] = []):
        """
        Парсинг каталога заданного магазина

        Parameters
        ----------
        region: str, регион
        city: str, город
        address: str, адрес магазина
        categories_needed: Optional[List[str]] (default=[]), список категорий, которые нужно спарсить.
            По дефолу -- все категории

        Returns
        -------
        local_items: LocalCatalogItems, товары каталога выбранного магазина

        """
        self.close_popup_age()
        self.shop_selector.select_shop(region, city, address)
        self.driver.get(self.catalog_link)

        # Выкачиваем список категорий
        try:
            catalog_top_sections = (
                WebDriverWait(self.driver, DEFAULT_DELAY)
                .until(EC.presence_of_element_located((By.CLASS_NAME, 'catalog_top_sections')))
            )
            catalog_element_list = catalog_top_sections.find_elements_by_class_name('catalog_top_sections__item')
        except TimeoutException:
            raise TimeoutException("Не получилось загрузить каталог")

        categories = []
        for element in catalog_element_list:
            link = (
                element.find_element_by_class_name('catalog_top_sections__item__name')
                .find_element_by_tag_name('a')
            )
            name = link.text
            link = link.get_attribute('href')
            if name in categories_needed or not categories_needed:
                categories.append((name, link))

        local_items = LocalCatalogItems(region, city, address)

        for cat_name, link in categories:
            print(f'parsing {cat_name}')
            self.driver.get(link)
            time.sleep(1)

            parse_another_page = True
            while parse_another_page:
                items = self.driver.find_elements_by_class_name('catalog_product_item')
                for item in items:
                    local_items.add_element(item, cat_name)
                scroller = Scroller(self.driver)
                parse_another_page = scroller.next_page()

        return local_items
