from domain.weather.pipelines.general_36hour.update import update as update_36
from domain.weather.pipelines.three_days.update import update as update_three_day
from domain.weather.pipelines.one_week.update import update as update_one_week
from domain.weather.pipelines.delete_expired_data import purge_expired_data

def run():
    update_36()
    update_three_day()
    update_one_week()
    purge_expired_data()

    
if __name__ == "__main__":
    run()