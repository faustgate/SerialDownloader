#!/usr/bin/env python3
# coding=utf-8

import os
import requests as r
from lxml import html
import sqlite3
import hashlib
from urllib.parse import urlparse
from os.path import splitext, basename
from lxml import etree


class SerialWorker(object):
    def __init__(self):
        self.BASE_URL = 'http://seasonvar.ru'
        self.SERIAL_LIST_URL_TPL = '{}/index.php'.format(self.BASE_URL)
        DB_NAME = os.path.join(os.path.dirname(__file__), "seasonvar.db")
        self.cache_location = os.path.join(os.path.dirname(__file__), "cache")
        self.con = sqlite3.connect(DB_NAME)
        self.cur = self.con.cursor()

        self.serial_list_xpath = '//div/div/a'
        self.poster_xpath = '//span[contains(@class, "poster")]/img/@src'
        self.name_xpath = '//h1[@class="pgs-sinfo-title"]/text()'
        self.descr_xpath = '//p[@itemprop="description"]/text()'
        self.country_xpath = '//div[text()[contains(., "Страна")]]/span[last()]/text()'
        self.strings_to_remove_from_names = ['Сериал', 'Субтитры', 'онлайн']
        self.download_cmd_tpl = 'wget -O "serials/{0}/{1}{2}" {3} > /dev/null 2>&1 &'

        self.init_db()

        self.existing_serials = self.get_existing_serial_pages()

    def init_db(self):
        self.cur.execute("CREATE TABLE IF NOT EXISTS serials ("
                         "id INTEGER PRIMARY KEY, "
                         "page VARCHAR, "
                         "serial_name_rus VARCHAR, "
                         "serial_name_original VARCHAR, "
                         "description VARCHAR, "
                         "poster_remote VARCHAR, "
                         "poster_local VARCHAR, "
                         "country VARCHAR)")

    def clear_name(self, src_name):
        for elem in self.strings_to_remove_from_names:
            src_name = src_name.replace(elem, '')
        while "  " in src_name:
            src_name = src_name.replace("  ", " ")
        return src_name.strip()

    def get_existing_serial_pages(self):
        serial_list = []
        for result in self.cur.execute("SELECT page FROM serials;"):
            serial_list.append(result[0])
        return serial_list

    def get_poster_url(self, src_url):
        if 'http://' not in src_url:
            return self.BASE_URL + src_url
        return src_url

    def get_serial_details(self, serial_url):
        res = {'url': serial_url}
        serial_info = html.fromstring(r.get(serial_url).text)
        poster = self.get_poster_url(serial_info.xpath(self.poster_xpath)[0])
        name = self.clear_name(serial_info.xpath(self.name_xpath)[0])
        descr = str(serial_info.xpath(self.descr_xpath)[0]).strip()
        country = str(serial_info.xpath(self.country_xpath)[0]).strip()
        res.update({'poster': poster, 'name': name, 'description': descr, 'country':country})
        return res

    def add_poster_to_cache(self, poster_url):
        hasher = hashlib.md5()
        img = r.get(poster_url).content
        hasher.update(img)
        name = hasher.hexdigest()
        if not os.path.isdir(self.cache_location):
            os.mkdir(self.cache_location)
        folder_name = name[:2]
        if not os.path.isdir(os.path.join(self.cache_location, folder_name)):
            os.mkdir(os.path.join(self.cache_location, folder_name))
        local_img_path = os.path.join(self.cache_location, folder_name, name)
        if not os.path.isfile(local_img_path):
            with open(local_img_path, 'wb') as img_file:
                img_file.write(img)
        return name

    def download_serial(self, serial_id):
        serial_page_url = self.get_serial_info(serial_id)[0]['link']
        serial_page_content = r.get(serial_page_url).text
        serial_page = html.fromstring(serial_page_content)
        serial_name = self.clear_name(serial_page.xpath(self.name_xpath)[0])
        series_list = serial_page.xpath(
            '/html/body/div[4]/div[2]/div/div[2]/div[5]/div/script')[0].text
        series_list = series_list.replace("vk.init();\nvk.show(1,[[", '')
        series_list = series_list.replace("]]);", '').replace("'", '').strip()
        series_list = series_list.split(',')
        for series_page_url in series_list:
            series_page_content = r.get(series_page_url).text
            series_page = html.fromstring(series_page_content)
            series = series_page.xpath('/html/body/script')[0].text.strip()
            start_point = str(series).index('<video')
            end_point = str(series).index('</video>')
            src_data = series[start_point:end_point] + '</video>'
            src_data = html.fromstring(src_data)
            video_url = src_data.xpath('source/@src')[0].replace(
                '?m3u8=hls.m3u8', '')
            serie_name, file_ext = splitext(basename(urlparse(video_url).path))
            if not os.path.isdir('serials/{0}'.format(serial_name)):
                os.mkdir('serials/{0}'.format(serial_name))

            try:
                sub_url = src_data.xpath('track/@src')[0]
                os.system(self.download_cmd_tpl.format(serial_name,
                                                       serie_name,
                                                       '.vtt',
                                                       sub_url))
            except IndexError:
                print("Seems like there is no subs for {}".format(serie_name))

            os.system(self.download_cmd_tpl.format(serial_name,
                                                   serie_name,
                                                   file_ext,
                                                   video_url))

            print(series_list)

    def add_serial_to_db(self, serial_info):
        self.cur.execute('INSERT INTO serials ('
                         'page, '
                         'serial_name_rus, '
                         'description, '
                         'poster_remote, '
                         'poster_local, '
                         'country) VALUES (?,?,?,?,?,?)',
                         (serial_info['url'],
                          serial_info['name'],
                          serial_info['description'],
                          serial_info['poster'],
                          serial_info['l_poster'],
                          serial_info['country']))

    def fill_in_db(self):
        search_term = 'filter%5BquotT%5D%5B%5D=%D0%A1%D1%83%D0%B1%D1%82%D0%B8%D1%82%D1%80%D1%8B'
        page_res = r.post(self.SERIAL_LIST_URL_TPL,
                          data=search_term,
                          headers={
                              "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                          allow_redirects=False)
        if page_res.status_code != 200:
            return
        raw_page = page_res.text
        parsed_page = html.fromstring(raw_page)
        serial_cards = parsed_page.xpath(self.serial_list_xpath)
        for serial_card in serial_cards:
            serial_url = self.BASE_URL + serial_card.xpath('@href')[0]
           # last_update_date = serial_card.xpath('div[@class="short-title"]/span/noindex/text()')[0]

            if serial_url not in self.existing_serials:
                serial_details = self.get_serial_details(serial_url)
                l_poster = self.add_poster_to_cache(serial_details['poster'])
                serial_details['l_poster'] = l_poster
              #  serial_details['last_update'] = last_update_date
                self.add_serial_to_db(serial_details)
            else:
                pass
            self.con.commit()

    def get_serial_info(self, serial_id='all'):
        results = []
        query = "SELECT * FROM serials;"
        if serial_id != 'all':
            query = query.replace(';', ' WHERE id="{0}"'.format(serial_id))
        res = self.cur.execute(query)
        res1 = res.fetchall()
        for result in res1:
            cur_res = {'id': result[0],
                       'link': result[1],
                       'name': result[2],
                       'desc': result[4],
                       'pstr': result[6] if result[6] != '' else result[5]}
            results.append(cur_res)
        return results


if __name__ == '__main__':
    SW = SerialWorker()
    SW.fill_in_db()
