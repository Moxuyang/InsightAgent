"""Create a public weather skill, employee and owner-only demo group; no model key needed."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models.db import get_connection
from app.models.skill import SkillRepository
from app.models.digital_employee import DigitalEmployeeRepository
from app.models.collaboration import CollabGroupRepository, CollabMemberRepository
from app.models.user import UserRepository

WEATHER_URL = ('https://api.open-meteo.com/v1/forecast?latitude=30.67&longitude=104.06'
               '&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m'
               '&timezone=Asia%2FShanghai&forecast_days=1')


def setup(username='admin'):
    owner = UserRepository.get_user_by_username(username)
    if not owner:
        raise ValueError('请先启动项目创建账号，或指定已存在的用户名')
    with get_connection() as conn:
        row = conn.execute('SELECT id FROM skills WHERE name=?', ('成都天气查询 · Open-Meteo',)).fetchone()
    skill = row['id'] if row else SkillRepository.create(
        '成都天气查询 · Open-Meteo', description='查询成都固定位置当前气温、体感温度、湿度、风速和降水。数据来自 Open-Meteo 天气模型；不支持自动切换城市或历史日期。',
        api_url=WEATHER_URL, api_method='GET')
    with get_connection() as conn:
        row = conn.execute('SELECT id FROM digital_employees WHERE name=?', ('成都天气助手',)).fetchone()
    employee = row['id'] if row else DigitalEmployeeRepository.create(
        '成都天气助手', '查询成都固定坐标当前天气；直接返回公开天气接口数据，无需大模型。', None, str(skill), 1)
    with get_connection() as conn:
        row = conn.execute('SELECT id FROM collab_groups WHERE name=? AND creator_id=?', ('天气查询演示', owner['id'])).fetchone()
    group = row['id'] if row else CollabGroupRepository.create('天气查询演示', owner['id'], '真实 API 技能演示：@成都天气助手 查询成都现在的天气')
    members = CollabMemberRepository.get_members(group)
    if not any(m['member_type']=='employee' and m['member_id']==employee for m in members):
        CollabMemberRepository.add_member(group, 'employee', employee)
    return {'skill_id': skill, 'employee_id': employee, 'group_id': group}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', default='admin', help='群组所有者的现有用户名')
    print(setup(parser.parse_args().username))
