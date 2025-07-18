import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import html
import re
import requests # Adicionado para requisições HTTP
import difflib # Adicionado para comparação de strings
from urllib.parse import unquote
import unicodedata

# --- Configuração ---
SCHEDULE_PAGE_URL = "http://192.168.68.19:3000/schedule/"
M3U8_OUTPUT_FILENAME = "schedule_playlist.m3u8"
EPG_OUTPUT_FILENAME = "epg.xml"
EPG_EVENT_DURATION_HOURS = 2
GROUP_SORT_ORDER = ["Futebol", "Basquete", "Futebol Americano", "Automobilismo", "Hóquei no Gelo", "Programas de TV", "Beisebol"]
EPG_PAST_EVENT_CUTOFF_HOURS = 1

# Repositório de logos do GitHub
GITHUB_API_URL = "https://api.github.com/repos/tv-logo/tv-logos/contents/countries"

# --- ALTERAÇÃO 1: Adicionada uma constante para o ícone padrão ---
DEFAULT_SPORT_ICON = "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/sports.png?raw=true"

SPORT_ICON_MAP = {
    "Futebol": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/soccer.png?raw=true",
    "Basquete": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/basketball.png?raw=true",
    "Futebol Americano": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/americanfootball.png?raw=true",
    "Tênis": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/tennis.png?raw=true",
    "Sinuca": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/snooker.png?raw=true",
    "Automobilismo": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/motorsport.png?raw=true",
    "Programas de TV": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/tv.png?raw=true", 
    "Beisebol": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/baseball.png?raw=true",    
    "Cricket": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/cricket.png?raw=true",
    "Athletics": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/Athletics.png?raw=true",
    "Ciclismo": DEFAULT_SPORT_ICON,
    "Golfe": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/golf.png?raw=true",
    "Corrida de Cavalos": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/horse.png?raw=true",
    "Rugby Union": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/rugby.png?raw=true",
    "Hóquei no Gelo": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/hockey.png?raw=true",
    "Water Sports": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/water.png?raw=true",
    "Water polo": "https://github.com/raphaelfuchter/StepDaddyLiveHD-Lives/blob/main/Logos/water.png?raw=true",
}
SPORT_TRANSLATION_MAP = {
    "Soccer": "Futebol",
    "Basketball": "Basquete",
    "Am. Football": "Futebol Americano",
    "Tennis": "Tênis",
    "Motorsport": "Automobilismo",
    "Snooker": "Sinuca",
    "Athletics": "Atletismo",
    "Baseball": "Beisebol",
    "Cricket": "Críquete",
    "Cycling": "Ciclismo",
    "Horse Racing": "Corrida de Cavalos",
    "Golf": "Golfe",
    "Water Sports": "Esportes Aquáticos",
    "Water polo": "Polo Aquático",
    "TV Shows": "Programas de TV",
    "Ice Hockey": "Hóquei no Gelo"
}
# --- Fim da Configuração ---

def get_all_logo_urls_from_github(api_url: str) -> dict:
    """
    Busca recursivamente todos os logos do repositório e retorna um dicionário
    mapeando o nome do canal (sem extensão) para a URL do logo.
    """
    print("\nBuscando catálogo de logos do GitHub... Isso pode levar um momento.")
    logo_cache = {}
    
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        countries = response.json()

        for country in countries:
            if country['type'] == 'dir':
                country_resp = requests.get(country['url'])
                country_resp.raise_for_status()
                logos = country_resp.json()
                
                for logo in logos:
                    if logo['type'] == 'file' and logo['name'].endswith(('.png', '.jpg', '.svg')):
                        # Normaliza o nome do arquivo para usar como chave
                        file_name_without_ext = os.path.splitext(unquote(logo['name']))[0]
                        # A URL de download é a forma mais confiável
                        logo_cache[file_name_without_ext] = logo['download_url']

    except requests.exceptions.RequestException as e:
        print(f"  AVISO: Falha ao buscar logos do GitHub. Usando apenas logos de esporte. Erro: {e}")
        return {}

    print(f"Catálogo de {len(logo_cache)} logos carregado com sucesso.")
    return logo_cache

def normalize_text(text: str) -> str:
    """Normaliza texto para comparação: minúsculas, sem acentos, remove 'hd', 'sd', etc."""
    text = text.lower()
    # Remove acentos
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    # Remove termos comuns e caracteres especiais
    text = re.sub(r'\b(hd|sd|fhd|uhd|4k|24h|ao vivo)\b', '', text)
    text = re.sub(r'[^a-z0-9]', '', text)
    return text

def find_best_logo_url(source_name: str, logo_cache: dict, sport_icon: str) -> str:
    """Encontra a melhor URL de logo para o source_name, com fallback para o ícone do esporte."""
    if not logo_cache or not source_name:
        return sport_icon

    normalized_source = normalize_text(source_name)
    if not normalized_source:
        return sport_icon

    # Normaliza as chaves do cache para a busca
    normalized_keys = {normalize_text(k): k for k in logo_cache.keys()}
    
    # Encontra a correspondência mais próxima
    best_match_normalized = difflib.get_close_matches(normalized_source, normalized_keys.keys(), n=1, cutoff=0.6)

    if best_match_normalized:
        original_key = normalized_keys[best_match_normalized[0]]
        return logo_cache[original_key]
    
    return sport_icon


def sanitize_id(name: str) -> str:
    """Limpa o nome para criar um ID válido sem espaços/caracteres especiais."""
    name = name.replace(' ', '')
    name = re.sub(r'[^a-zA-Z0-9.-]', '', name)
    return name

def reformat_event_name(event_name: str) -> str:
    """Reformata o nome do evento para 'Equipes : Campeonato'."""
    if ' : ' in event_name:
        parts = event_name.rsplit(' : ', 1)
        if len(parts) == 2:
            campeonato = parts[0].strip()
            equipes = parts[1].strip()
            return f"{equipes} : {campeonato}"
    return event_name

def get_initial_todo_list(driver, url: str) -> list:
    """Carrega a página, desativa o filtro e extrai a lista de tarefas."""
    todo_list = []
    print(f"Navegando para: {url} para fazer o mapeamento inicial de eventos...")
    driver.get(url)
    try:
        print("Verificando o estado do botão 'Hide past events'...")
        switch_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button[role='switch']"))
        )
        if switch_button.get_attribute('data-state') == 'checked':
            print("  O botão está LIGADO. Desligando para mostrar todos os eventos...")
            switch_button.click()
            time.sleep(3)
            print("  Botão DESLIGADO.")
        else:
            print("  O botão já está DESLIGADO. Nenhuma ação necessária.")
    except Exception as e:
        print(f"  AVISO: Não foi possível interagir com o botão 'Hide past events'. O script continuará. Erro: {e}")

    print("\nAguardando a lista de eventos carregar...")
    WebDriverWait(driver, 15).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.rt-Card h1.rt-Heading"))
    )
    print("Eventos detectados. Lendo a estrutura da página...")
    time.sleep(3) 

    soup = BeautifulSoup(driver.page_source, 'lxml')
    all_cards_on_page = soup.find_all('div', class_='rt-Card')

    for card in all_cards_on_page:
        event_name_tag = card.find('h1', class_='rt-Heading')
        if not event_name_tag:
            continue
        
        original_event_name = event_name_tag.get_text(strip=True)
        reformatted_name = reformat_event_name(original_event_name)
        
        sport_tag = card.find('span', class_='rt-Badge')
        time_tag = card.find('time')
        
        button_texts = []
        button_container = card.find('div', class_='css-qslnu8')
        if button_container:
            buttons = button_container.find_all('button')
            button_texts = [b.get_text(strip=True) for b in buttons if b.get_text(strip=True)]

        if all([original_event_name, sport_tag, time_tag, button_texts]):
            original_sport_name = sport_tag.get_text(strip=True)
            translated_sport_name = SPORT_TRANSLATION_MAP.get(original_sport_name, original_sport_name)
            todo_list.append({
                'original_name': original_event_name,
                'display_name': reformatted_name,
                'sport': translated_sport_name,
                'start_timestamp_ms': time_tag.get('datetime'),
                'button_texts': button_texts
            })
            
    print(f"Mapeamento inicial concluído. {len(todo_list)} eventos com fontes encontradas.")
    return todo_list

def process_events_by_content(driver, todo_list: list) -> list:
    """Processa a lista de tarefas, navegando e 'carimbando' cada stream com sua ordem original."""
    stream_list = []
    original_order_counter = 0 
    
    for event_data in todo_list:
        event_name_for_search = event_data['original_name']
        event_name_for_display = event_data['display_name']
        print(f"\nProcessando evento: '{event_name_for_display}'")
        
        for button_text in event_data['button_texts']:
            try:
                print(f"  Procurando e clicando na fonte: '{button_text}'...")
                safe_event_name_for_search = event_name_for_search.replace('"', "'")
                safe_button_text = button_text.replace('"', "'")
                button_xpath = f"//div[.//h1[normalize-space()=\"{safe_event_name_for_search}\"]]//button[normalize-space()=\"{safe_button_text}\"]"
                
                button_to_click = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, button_xpath))
                )
                button_to_click.click()
                
                WebDriverWait(driver, 10).until(EC.url_contains('/watch/'))
                watch_url = driver.current_url
                stream_id = watch_url.split('/')[-1]
                print(f"    ID real encontrado: {stream_id}")

                stream_list.append({
                    'id': stream_id,
                    'event_name': event_data['display_name'],
                    'sport': event_data['sport'],
                    'source_name': button_text,
                    'start_timestamp_ms': event_data['start_timestamp_ms'],
                    'original_order': original_order_counter
                })
                original_order_counter += 1
            except Exception as e:
                print(f"    Ocorreu um erro ao processar o botão '{button_text}': {e}")
            
            finally:
                print("    Retornando para a página de eventos...")
                driver.get(SCHEDULE_PAGE_URL)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.rt-Card h1.rt-Heading"))
                )
    return stream_list

def generate_m3u8_content(stream_list: list, base_url: str, logo_cache: dict) -> str:
    """Gera o M3U8 com um ID único por evento para lincar com o EPG e logos dinâmicos."""
    m3u8_lines = ["#EXTM3U"]
    if not stream_list: return "\n".join(m3u8_lines)
    
    print(f"\nOrdenando {len(stream_list)} streams para o arquivo M3U8...")
    sort_priority_lower = [s.lower() for s in GROUP_SORT_ORDER]
    def get_sort_key(stream):
        sport = stream.get("sport", "").strip().lower()
        primary_key = sort_priority_lower.index(sport) if sport in sort_priority_lower else len(sort_priority_lower)
        secondary_key = sport
        tertiary_key = stream.get('original_order', 999)
        return (primary_key, secondary_key, tertiary_key)
    stream_list.sort(key=get_sort_key)
    
    for stream in stream_list:
        display_title = stream.get('event_name', "Evento Desconhecido")
        sport_group = stream.get("sport", "Geral")
        channel_name = stream.get('source_name', "Canal Desconhecido")
        
        unique_id = sanitize_id(f"evt.{channel_name}.{stream['id']}")
        
        # --- ALTERAÇÃO 2: Usa a constante DEFAULT_SPORT_ICON como fallback ---
        # Encontra o melhor logo dinamicamente
        sport_icon_fallback = SPORT_ICON_MAP.get(sport_group, DEFAULT_SPORT_ICON)
        logo_url = find_best_logo_url(channel_name, logo_cache, sport_icon_fallback)
        
        logo_attribute = f' tvg-logo="{logo_url}"' if logo_url else ''
        
        extinf_line = f'#EXTINF:-1 tvg-id="{unique_id}"{logo_attribute} group-title="{sport_group}",{display_title}'
        stream_url = f"{base_url.strip('/')}/stream/{stream['id']}.m3u8"
        
        m3u8_lines.append(extinf_line)
        m3u8_lines.append(stream_url)
    return "\n".join(m3u8_lines)

def generate_xmltv_epg(stream_list: list, logo_cache: dict) -> str:
    """Gera um EPG de dia inteiro para cada evento com logos dinâmicos."""
    if not stream_list: return ""
    print(f"Formatando {len(stream_list)} streams para o arquivo EPG XML...")
    
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv>']
    
    # 1. Cria um <channel> para CADA stream, usando um ID único
    for stream in stream_list:
        unique_id = sanitize_id(f"evt.{stream['source_name']}.{stream['id']}")
        channel_display_name = stream.get('source_name', 'Canal')
        sport_group = stream.get("sport")

        # Encontra o melhor logo dinamicamente
        sport_icon_fallback = SPORT_ICON_MAP.get(sport_group, DEFAULT_SPORT_ICON)
        logo_url = find_best_logo_url(channel_display_name, logo_cache, sport_icon_fallback)

        xml_lines.append(f'  <channel id="{unique_id}">')
        xml_lines.append(f'    <display-name>{html.escape(channel_display_name)}</display-name>')
        if logo_url:
            xml_lines.append(f'    <icon src="{logo_url}" />')
        xml_lines.append('  </channel>')

    # 2. Cria a programação para CADA stream
    for stream in stream_list:
        try:
            unique_id = sanitize_id(f"evt.{stream['source_name']}.{stream['id']}")
            timestamp_ms = int(stream['start_timestamp_ms'])
            start_dt_utc = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            end_dt_utc = start_dt_utc + timedelta(hours=EPG_EVENT_DURATION_HOURS)
            
            safe_event_name = html.escape(stream['event_name'])
            safe_channel_name = html.escape(stream['source_name'])
            safe_sport_name = html.escape(stream['sport'])

            # --- ALTERAÇÃO INÍCIO: Lógica unificada para todos os dias ---
            # Define o início e o fim do dia do evento (00:00 às 23:59:59)
            event_day_start_utc = start_dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            event_day_end_utc = event_day_start_utc + timedelta(days=1)

            # Bloco 1: "Evento não iniciado" (do início do dia até o começo do evento)
            if start_dt_utc > event_day_start_utc:
                start_str_before = event_day_start_utc.strftime('%Y%m%d%H%M%S') + " +0000"
                stop_str_before = start_dt_utc.strftime('%Y%m%d%H%M%S') + " +0000"
                
                start_str_before = stop_str_before - timedelta(days=2)
                
                xml_lines.append(f'  <programme start="{start_str_before}" stop="{stop_str_before}" channel="{unique_id}">')
                xml_lines.append(f'    <title lang="pt">Evento não iniciado</title>')
                xml_lines.append(f'    <desc lang="pt">Aguardando o início do evento programado.</desc>')
                xml_lines.append('  </programme>')

            # Bloco 2: O evento real
            start_str_real = start_dt_utc.strftime('%Y%m%d%H%M%S') + " +0000"
            end_str_real = end_dt_utc.strftime('%Y%m%d%H%M%S') + " +0000"
            xml_lines.append(f'  <programme start="{start_str_real}" stop="{end_str_real}" channel="{unique_id}">')
            xml_lines.append(f'    <title lang="pt">{safe_channel_name}</title>')
            xml_lines.append(f'    <desc lang="pt">{safe_event_name}</desc>')
            xml_lines.append(f'    <category lang="pt">{safe_sport_name}</category>')
            xml_lines.append('  </programme>')

            # Bloco 3: "Evento finalizado" (do fim do evento até o fim do dia)
            if end_dt_utc < event_day_end_utc:
                start_str_after = end_dt_utc.strftime('%Y%m%d%H%M%S') + " +0000"
                stop_str_after = event_day_end_utc.strftime('%Y%m%d%H%M%S') + " +0000"
                
                stop_str_after = stop_str_after + timedelta(days=3)
                
                xml_lines.append(f'  <programme start="{start_str_after}" stop="{stop_str_after}" channel="{unique_id}">')
                xml_lines.append(f'    <title lang="pt">Evento finalizado</title>')
                xml_lines.append(f'    <desc lang="pt">A programação ao vivo deste evento foi encerrada.</desc>')
                xml_lines.append('  </programme>')
            # --- ALTERAÇÃO FIM ---
            
        except (ValueError, TypeError):
            continue
            
    xml_lines.append('</tv>')
    return "\n".join(xml_lines)

def main():
    """Função principal que usa Selenium para navegação complexa."""
    print("--- Gerador de Playlist e EPG (v64 - Logos Dinâmicos) ---")
    
    # Busca e armazena em cache os logos do GitHub no início
    logo_cache = get_all_logo_urls_from_github(GITHUB_API_URL)

    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--log-level=3')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    stream_data = []
    base_url = ""
    try:
        base_url = SCHEDULE_PAGE_URL.rsplit('/', 2)[0]
        todo_list = get_initial_todo_list(driver, SCHEDULE_PAGE_URL)
        if todo_list:
            stream_data = process_events_by_content(driver, todo_list)
    finally:
        print("\nProcesso de extração finalizado. Fechando o navegador.")
        driver.quit()

    if not stream_data:
        print("\nNenhum stream foi extraído com sucesso.")
        return

    now_utc = datetime.now(timezone.utc)
    cutoff_time = now_utc - timedelta(hours=EPG_PAST_EVENT_CUTOFF_HOURS)
    
    filtered_stream_data = []
    for stream in stream_data:
        try:
            timestamp_ms = int(stream['start_timestamp_ms'])
            start_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            end_dt = start_dt + timedelta(hours=EPG_EVENT_DURATION_HOURS)
            if end_dt >= cutoff_time:
                filtered_stream_data.append(stream)
        except (ValueError, TypeError):
            continue

    print(f"\nStreams extraídos: {len(stream_data)}. Streams após filtro de tempo: {len(filtered_stream_data)}.")
    
    if not filtered_stream_data:
        print("Nenhum stream restou após a filtragem de tempo.")
        m3u8_content = "#EXTM3U"
        epg_content = '<?xml version="1.0" encoding="UTF-8"?>\n<tv></tv>'
    else:
        # Passa o cache de logos para as funções geradoras
        m3u8_content = generate_m3u8_content(filtered_stream_data, base_url, logo_cache)
        epg_content = generate_xmltv_epg(filtered_stream_data, logo_cache)

    try:
        with open(M3U8_OUTPUT_FILENAME, "w", encoding="utf-8") as f:
            f.write(m3u8_content)
        print(f"✅ Sucesso! O arquivo '{M3U8_OUTPUT_FILENAME}' foi gerado.")
    except IOError as e:
        print(f"\nERRO: Falha ao salvar o arquivo M3U8. Detalhe: {e}")

    if epg_content:
        try:
            with open(EPG_OUTPUT_FILENAME, "w", encoding="utf-8") as f:
                f.write(epg_content)
            print(f"✅ Sucesso! O arquivo '{EPG_OUTPUT_FILENAME}' foi gerado.")
        except IOError as e:
            print(f"\nERRO: Falha ao salvar o arquivo EPG. Detalhe: {e}")

if __name__ == "__main__":
    main()