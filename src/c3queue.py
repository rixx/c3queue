import csv
import os
from collections import defaultdict

import aiohttp_jinja2
import aiofiles
import jinja2
import pygal
from aiohttp import web
from dateutil import parser


DATA_PATH = ''
C3SECRET = os.environ.get('C3QUEUE_SECRET')


def structure_data(data):
    result = defaultdict(lambda: defaultdict(list))
    for entry in data:
        entry['duration'] = round((entry['pong'] - entry['ping']).seconds / 60, 1)
        ping = entry['ping']
        result[ping.year][ping.day].append(entry)
    return result


@aiohttp_jinja2.template('stats.html')
async def stats(request):
    data = await parse_data()
    data = structure_data(data)
    charts = []
    for year in list(data.keys())[::-1]:
        for number, day in data[year].items():  # TODO: combine day 1 of all years, etc
            first_ping = day[0]['ping']
            line_chart = pygal.Line(x_label_rotation=40, interpolate='cubic', show_legend=False, title='Day {}, {}'.format(number - 26, year), height=300)
            line_chart.x_labels = map(lambda d: d.strftime('%H:%M'), [d['ping'] for d in day])
            line_chart.value_formatter = lambda x:  '{} minutes'.format(x)
            line_chart.add('Waiting time', [d['duration'] for d in day])
            charts.append(line_chart.render(is_unicode=True))
    return {'charts': charts}


async def pong(request):
    if not 'Authorization' in request.headers or request.headers['Authorization'] != C3SECRET:
        return aiohttp_jinja2.render_template('405.html', request, {})
    try:
        data = await request.post()
    except:
        return aiohttp_jinja2.render_template('405.html', request, {})
    if 'ping' in data and 'pong' in data:
        try:
            ping = parser.parse(data['ping'])
            pong = parser.parse(data['pong'])
        except:
            return aiohttp_jinja2.render_template('405.html', request, {})
        else:
            await write_line(ping, pong)
            return web.Response(status=201)
    return aiohttp_jinja2.render_template('405.html', request, {'data': data})


async def data(request):
    async with aiofiles.open(DATA_PATH) as d:
        data = await d.read()
    return web.Response(text=data)


async def parse_data():
    result = []
    async with aiofiles.open(DATA_PATH) as d:
        async for row in d:
            if row.strip() == 'ping,pong':
                continue
            ping, pong = row.split(',')
            ping = parser.parse(ping.strip('"'))
            pong = parser.parse(pong.strip('"'))
            result.append({'ping': ping, 'pong': pong, 'rtt': (pong - ping) if (ping and pong) else None})
    return result


async def write_line(ping, pong):
    async with aiofiles.open(DATA_PATH, 'a') as d:
        await d.write('{},{}\n'.format(ping.isoformat(), pong.isoformat()))


async def get_data_path():
    global DATA_PATH
    DATA_PATH = os.environ.get('C3QUEUE_DATA', './c3queue.csv')
    if not os.path.exists(DATA_PATH):
        with aiofiles.open(DATA_PATH, 'w') as d:
            d.write('ping,pong\n')


async def main(argv):
    app = web.Application()
    app.add_routes([web.get('/', stats)])
    app.add_routes([web.post('/pong', pong)])
    app.add_routes([web.get('/data', data)])
    app.add_routes([web.static('/static', os.path.join(os.path.dirname(__file__), 'static'))])
    aiohttp_jinja2.setup(app, loader=jinja2.PackageLoader('c3queue', 'templates'))
    await get_data_path()
    return app
