import genshinstats as gs
import discord
from discord import ui
from enkanetwork import EnkaNetworkAPI
from discord.ui import View
import aiohttp
import sqlite3
import time


#TOKEN
TOKEN = 'xxxxxx'

intents=discord.Intents.all()
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

modal_id = 0
bot_name = ""

conn=sqlite3.connect("./genshin.db", check_same_thread=False)
c=conn.cursor()
data=c.fetchone()
c.execute("CREATE TABLE IF NOT EXISTS genshin(modalid str primary key, selectid str, mapid str, cancelid str, uid int)")

@client.event
async def on_ready():
    global bot_name
    print("起動")
    bot_name=client.user.name
    await client.change_presence(activity=discord.Game(name="💥げんしんいんぱくと"))
    await tree.sync()

#モーダルポップアップウィンドウとプレイヤーステータスの表示
class GenshinModal(ui.Modal):
    def __init__(self):
        super().__init__(
            title="原神のUIDを入力してください"
        )

        self.contents = ui.TextInput(
            label="UID",
            style= discord.TextStyle.short,
            placeholder="例:847262599",
            required=True,
        )
        self.add_item(self.contents)

    #UID入力後にプレイヤーステータス走査
    async def on_submit(self, interaction: discord.Interaction):
        global modal_id

        await interaction.response.send_message(content="キャラクターステータス取得中...")
        
        #channel_id=interaction.channel_id
        #channel = await interaction.guild.fetch_channel(channel_id)

        try:
            uid = int(self.contents.value)
        except Exception as e:
            print(e)
            await interaction.edit_original_response(content="入力に間違えがあるわ！")
            time.sleep(1.2)
            await interaction.delete_original_response()

            return

        client = EnkaNetworkAPI(lang='jp')

        try:
            async with client:
                data_enka = await client.fetch_user(uid)
        except Exception as e:
            print(e)
            await interaction.edit_original_response(content="そんな人いないわ！")
            time.sleep(1.2)
            await interaction.delete_original_response()
            return


        stats = await player_status(uid,data_enka)
        view = View(timeout=None)

        if stats == None:
            await interaction.edit_original_response(content="非公開ユーザだわ！")
            time.sleep(1.2)
            await interaction.delete_original_response()
            return

        modal_id = self.custom_id
        c.execute("INSERT INTO genshin VALUES(?, ?, ?, ?, ?)",(self.custom_id, "", "" , "", uid))
        conn.commit()

        try:
            view.add_item(enka(data_enka))
        except Exception as e:
            print(e)
            if "DataNotPublic" in str(e.__class__):
                pass
        
        try:
            #HoyoLabに公開している人はこの機能を使う
            gs.set_cookie(ltuid=XXXXXXXXXXXX, ltoken="YYYYYYYYYYYYYYYYYYYYY")
            data_hoyo = gs.get_all_user_data(uid,lang="ja-jp")
            view.add_item(hoyo(data_hoyo))
        #エラー時
        except Exception as e:
            print(e)
            if "DataNotPublic" in str(e.__class__):
                pass

        button = HugaButton("操作終了")
        view.add_item(button)

        try:
            #await channel.send(embed=stats,view=view,ephemeral=True)
            await interaction.edit_original_response(content=None,embed=stats,view=view)
            return
        except Exception as e:
            print(e)
            await interaction.edit_original_response(content="非公開ユーザかもね")
            time.sleep(1.2)
            await interaction.delete_original_response()
            c.execute("DELETE FROM genshin WHERE modalid=?", (modal_id,))
            conn.commit()

            return

class HugaListChara(discord.ui.Select):
    global modal_id
    def __init__(self,args,txt):
        options=[]
        for chara,lv in zip(args.keys(),args.values()):
            options.append(discord.SelectOption(label=chara + " " + str(lv) + "Lv", description=''))
        
        super().__init__(placeholder=txt, min_values=1, max_values=1, options=options)

        try:
            c.execute("UPDATE genshin set selectid =? WHERE modalid =?", (self.custom_id, modal_id))
            conn.commit()
        except Exception as e:
            print(e)
            pass

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="キャラデータ取得中...")

        c.execute("SELECT uid from genshin where selectid=?",(self.custom_id,))
        uid=c.fetchone()[0]

        client = EnkaNetworkAPI(lang='jp')
        async with client:
            data_enka = await client.fetch_user(uid)
        
        #マップやキャラクターのステータスを格納する
        status = None

        url = f"https://enka.network/u/{uid}/__data.json"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                resps = await response.json()

        try:
            for chara in data_enka.player.characters_preview:
                if self.values[0] == chara.name + " " + str(chara.level) + "Lv":
                    for i in range(len(resps["avatarInfoList"])):
                        if resps["avatarInfoList"][i]["avatarId"] == int(chara.id):
                            #キャラクターIDとプレイヤーのUID,Level,IconのURL
                            status = await character_status(chara.id,chara.name,chara.level,chara.icon.url,resps["avatarInfoList"][i],data_enka)
                            break
        except Exception as e:
            print(e)
            if "User's data is not public" in str(e.__class__) or "KeyError" in str(e.__class__):
                await interaction.message.edit(content="非公開キャラのようね")
                return
        
        #編集するのはembedのみであって，ボタンやセレクトメニューは編集しない
        await interaction.message.edit(content=None,embed=status)
        return
    

class HugaListMap(discord.ui.Select):
    global modal_id
    def __init__(self,args,txt):
        options=[]
        for item in args:
            options.append(discord.SelectOption(label=item, description=''))
    
        super().__init__(placeholder=txt, min_values=1, max_values=1, options=options)

        try:
            c.execute("UPDATE genshin set mapid =? WHERE modalid =?", (self.custom_id, modal_id))
            conn.commit()
        except Exception as e:
            print(e)
            pass


    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="マップデータ取得中")
        #HoyoLabに公開していないユーザは使用できない
        c.execute("SELECT uid from genshin where mapid=?",(self.custom_id,))
        uid=c.fetchone()[0]
        

        gs.set_cookie(ltuid=XXXXXXX, ltoken="YYYYYYYYYY")
        data_hoyo = gs.get_all_user_data(uid,lang="ja-jp")
        for i in range(len(data_hoyo['explorations'])):
            if self.values[0] == data_hoyo["explorations"][i]['name']:
                status = data_hoyo["explorations"][i]
                status = map_status(status)
                break
        #print(status)

        #編集するのはembedのみであって，ボタンやセレクトメニューは編集しない
        await interaction.message.edit(content=None,embed=status)
        return


#操作終了ボタンの実装
class HugaButton(discord.ui.Button): #HugaButtonはButtonのサブクラス
    global modal_id
    def __init__(self,txt:str):
        super().__init__(label=txt,style=discord.ButtonStyle.red)
        try:
            c.execute("UPDATE genshin set cancelid =? WHERE modalid =?", (self.custom_id, modal_id))
            conn.commit()
        except Exception as e:
            print(e)
            pass
    
    #async def on_timeout(self):
    #    c.execute("DELETE FROM genshin WHERE cancelid=?", (self.custom_id,))
    #    conn.commit()
    #    await interaction.message.delete()
    #    return

    async def on_error(self,interaction: discord.Interaction):
        print("On_error")
        c.execute("DELETE FROM genshin WHERE cancelid=?", (self.custom_id,))
        conn.commit()
        await interaction.message.delete()
        return

    async def callback(self, interaction: discord.Interaction):
        print("callback_delete")
        c.execute("DELETE FROM genshin WHERE cancelid=?", (self.custom_id,))
        conn.commit()
        await interaction.message.delete()
        #print("test")
        return


@tree.command(
    name="status",#コマンド名
    description="原神のuidを入力する"#コマンドの説明
)
async def uid(interaction: discord.Interaction):
    genshinModal = GenshinModal()
    await interaction.response.send_modal(genshinModal)


@tree.command(
    name="help",#コマンド名
    description="使い方とボットで閲覧できるものを見る"#コマンドの説明
)
async def help(interaction: discord.Interaction):
    global bot_name
    embed = discord.Embed( 
                        title=bot_name,
                        color=0x1e90ff,
                        description=f"使い方と私で見れるものが分かるわ!"
    )
    embed.add_field(name="`/status`",value="プレイヤーの所持キャラクターとマップの探索度を見れるわ!\n※プレイヤーの所持キャラクター情報を閲覧するにはゲームからキャラを詳細表示してね\n※マップ情報を見るためにはHoyoLabでプレイヤーデータを公開してね")
    embed.set_image(url="https://tfansite.jp/img/top/genshin/logo.png")
    await interaction.response.send_message(embed=embed)
    return


def enka(data_enka):
        chara_names = {}
        for chara in data_enka.player.characters_preview:
            chara_names[chara.name] = chara.level

        select = HugaListChara(chara_names,txt="所持キャラクター")
        #view.add_item(select)
        return select

def hoyo(data_hoyo):
    #HoyoLabに公開している人はこの機能を使う
    map_names = []
    for i in range(len(data_hoyo['explorations'])):
        map_names.append(data_hoyo['explorations'][i]['name'])

    #await channel.send(embed=stats,view=view)
    #HoyoLabに公開している人のみ使える機能

    select = HugaListMap(map_names,txt="マップ")
    return select

async def player_status(uid,data_enka):
        url = f"https://enka.network/u/{uid}/"
        private = 0

        try:
            embed = discord.Embed( 
                        title=f"{data_enka.player.nickname}の原神ステータス",
                        color=0x1e90ff,
                        description=f"uid: {uid}",
                        url=url
            )   
            icon_url = data_enka.player.icon.url.url
            embed.set_thumbnail(url=icon_url)
        except Exception as e:
            print(e)
            return None

        try:
            embed.add_field(inline=False,name="冒険ランク",value=data_enka.player.level)
            embed.add_field(inline=False,name="世界ランク",value=data_enka.player.world_level)
            #embed.add_field(inline=False,name="ステータスメッセージ",value=data_enka.player.signature)
            embed.add_field(inline=False,name="アチーブメント",value=data_enka.player.achievement)
            embed.add_field(inline=False,name="深鏡螺旋",value=str(data_enka.player.abyss_floor) + "-" + str(data_enka.player.abyss_room))

        except Exception as e:
            print(e)
            if "DataNotPublic" in str(e.__class__):
                private += 1
            elif "DataNotPublic" not in str(e.__class__):
                embed = discord.Embed( 
                        title=f"あら?エラーが発生したわ...しばらくしてからもう一回やってね",
                        color=0x1e90ff, 
                        url=url 
                )
                return embed
        
        try:
            gs.set_cookie(ltuid=179694940, ltoken="3DRoaeDyHN1gFhpvhJ8H1VSfVPuwRrD8fwbP6Nll")
            data_hoyo = gs.get_all_user_data(uid,lang="ja-jp")
            embed.add_field(inline=False,name="キャラ保持数",value=data_hoyo['stats']['characters'])
            embed.add_field(inline=False,name="普通の宝箱開放数",value=data_hoyo['stats']['common_chests'])
            embed.add_field(inline=False,name="良い宝箱開放数",value=data_hoyo['stats']['exquisite_chests'])
            embed.add_field(inline=False,name="豪華な宝箱開放数",value=data_hoyo['stats']['luxurious_chests'])
            embed.add_field(inline=False,name="プレイ日数",value=data_hoyo["stats"]['active_days'])
        except Exception as e:
            print(e)
            if "DataNotPublic" in str(e.__class__):
                private += 1
            elif "DataNotPublic" not in str(e.__class__):
                embed = discord.Embed( 
                        title=f"あら?エラーが発生したわ...しばらくしてからもう一回やってね",
                        color=0x1e90ff, 
                        url=url 
                )
                return embed

        if private < 2:
            return embed
        else:
            return None
#mapのステータスのUIを作る関数(embed)
def map_status(status):
    #map情報はenka.Netから収集出来るか調べる
    embed = discord.Embed(title=status['name']+'の探索度',description=str(status['explored']) + '%')
    embed.set_image(url=status['icon'])
    return embed


#キャラクターステータスのUIを作る関数(embed)
async def character_status(id,name,level,chara_url,resp,data_enka):
    global uid
    embed = discord.Embed(
        title=data_enka.player.nickname + "さんの" + name,
        color=0x1e90ff, 
        description=f"{level}lv", 
        )
    
    embed.set_thumbnail(url=chara_url)
    embed.add_field(inline=True,name="キャラレベル",value=f"{level}lv")
    embed.add_field(inline=True,name="キャラ突破レベル",value=str(resp["propMap"]["1002"]["ival"]))
    embed.add_field(inline=True,name="HP",
        value=f'{str(round(resp["fightPropMap"]["1"]))} + {str(round(resp["fightPropMap"]["2000"]) - round(resp["fightPropMap"]["1"]))} = {str(round(resp["fightPropMap"]["2000"]))}'
    )
    embed.add_field(inline=True,name="攻撃力",
        value=f'{str(round(resp["fightPropMap"]["4"]))} + {str(round(resp["fightPropMap"]["2001"]) - round(resp["fightPropMap"]["4"]))} = {str(round(resp["fightPropMap"]["2001"]))}'
    )
    embed.add_field(inline=True,name="防御力",
        value=f'{str(round(resp["fightPropMap"]["7"]))} + {str(round(resp["fightPropMap"]["2002"]) - round(resp["fightPropMap"]["7"]))} = {str(round(resp["fightPropMap"]["2002"]))}'
    )
    embed.add_field(inline=True,name="会心率",
        value=f'{str(round(resp["fightPropMap"]["20"] *100))}%'
    )
    embed.add_field(inline=True,name="会心ダメージ",
        value=f'{str(round(resp["fightPropMap"]["22"]*100))}%'
    )
    embed.add_field(inline=True,name="元素チャージ効率",
        value=f'{str(round(resp["fightPropMap"]["23"]*100))}%'
    )
    embed.add_field(inline=True,name="元素熟知",
        value=f'{str(round(resp["fightPropMap"]["28"]))}'
    )
    
    buf = 1
    if round(resp["fightPropMap"]["30"]*100) > 0:
        embed.add_field(inline=True,name="物理ダメージ",
            value=f'{str(round(resp["fightPropMap"]["30"]*100))}%'
        )
        buf += round(resp["fightPropMap"]["30"])
    elif round(resp["fightPropMap"]["40"]*100) > 0:
        embed.add_field(inline=True,name="炎元素ダメージ",
            value=f'{str(round(resp["fightPropMap"]["40"]*100))}%'
        )
        buf += round(resp["fightPropMap"]["40"])
    elif round(resp["fightPropMap"]["41"]*100) > 0:
        embed.add_field(inline=True,name="雷元素ダメージ",
            value=f'{str(round(resp["fightPropMap"]["41"]*100))}%'
        )
        buf += round(resp["fightPropMap"]["41"])
    elif round(resp["fightPropMap"]["42"]*100) > 0:
        embed.add_field(inline=True,name="水元素ダメージ",
            value=f'{str(round(resp["fightPropMap"]["42"]*100))}%'
        )
        buf += round(resp["fightPropMap"]["42"])
    elif round(resp["fightPropMap"]["43"]*100) > 0:
        embed.add_field(inline=True,name="草元素ダメージ",
            value=f'{str(round(resp["fightPropMap"]["43"]*100))}%'
        )
        buf += round(resp["fightPropMap"]["42"])
    elif round(resp["fightPropMap"]["44"]*100) > 0:
        embed.add_field(inline=True,name="風元素ダメージ",
            value=f'{str(round(resp["fightPropMap"]["44"]*100))}%'
        )
        buf += round(resp["fightPropMap"]["44"])
    elif round(resp["fightPropMap"]["45"]*100) > 0:
        embed.add_field(inline=True,name="岩元素ダメージ",
            value=f'{str(round(resp["fightPropMap"]["45"]*100))}%'
        )
        buf += round(resp["fightPropMap"]["45"])
    elif round(resp["fightPropMap"]["46"]*100) > 0:
        embed.add_field(inline=True,name="氷元素ダメージ",
            value=f'{str(round(resp["fightPropMap"]["46"]*100))}%'
        )
        buf += round(resp["fightPropMap"]["46"])

    temp = []
    for myvalue in resp["skillLevelMap"].values():
        temp.append(f"{myvalue}")
    embed.add_field(inline=False,name="天賦レベル",
        value="\n".join(temp)
    )

    for chara in data_enka.characters:
        if str(chara.id) == id:
            for equipment in chara.equipments:
                #聖遺物
                equip_name=()
                level = ""
                stat = ()
                stat_sub=[]
                #print("Flower" in equipment.detail.artifact_type)
                if "Flower" in str(equipment.detail.artifact_type):
                    equip_name= "花",equipment.detail.name

                if "Feather" in str(equipment.detail.artifact_type):
                    equip_name="羽",equipment.detail.name

                if "Sands" in str(equipment.detail.artifact_type):
                    equip_name="時計",equipment.detail.name

                if "Goblet" in str(equipment.detail.artifact_type):
                    equip_name="コップ",equipment.detail.name

                if "Circlet" in str(equipment.detail.artifact_type):
                    equip_name="頭",equipment.detail.name

                if "Unknown" in str(equipment.detail.artifact_type):
                    equip_name="武器",equipment.detail.name


                level = str(equipment.level)

                if "NUMBER" in str(equipment.detail.mainstats.type):
                    stat=equipment.detail.mainstats.name,str(equipment.detail.mainstats.value)
                    
                if "PERCENT" in str(equipment.detail.mainstats.type):
                    stat=equipment.detail.mainstats.name,str(equipment.detail.mainstats.value) + "%"
                
                
                for sub in equipment.detail.substats:
                    name_=""
                    value_=""
                    if "NUMBER" in str(sub.type):
                        name_=sub.name
                        value_=str(sub.value)
                    if "PERCENT" in str(sub.type):
                        name_=sub.name
                        value_=str(sub.value) + "%"

                    stat_sub.append(f"{name_}：{value_}")
                #print("===========")
                #print()
                
                embed.add_field(inline=True,name='聖遺物：'+ str(equip_name[0])+'\n'+ str(equip_name[1])+'\n'+ str(stat[0])+'：'+str(stat[1])+'\n'+ level+'lv'+'\n',value="\n".join(stat_sub))
            break

    return embed

client.run(TOKEN) #ボットのトークン
