from domain.air.pipelines.general_air_pollution.update import update
from domain.air.pipelines.delete_expire_data import purge_expired_data

def run():
    update()
    purge_expired_data()
    
if __name__ == "__main__":
    run()